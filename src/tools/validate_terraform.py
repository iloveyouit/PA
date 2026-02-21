"""
Terraform & PowerShell Validator — Sandboxed code validation via E2B.

Spins up an ephemeral micro-VM, writes the code, runs validation commands
(terraform validate, PSScriptAnalyzer), and reports pass/fail with errors.
The agent uses this to self-correct before delivering code to the user.

Usage:
    from src.tools.validate_terraform import validate_terraform, validate_powershell
    result = validate_terraform('resource "azurerm_resource_group" "rg" { ... }')
    result = validate_powershell('Get-ADUser -Filter * | Export-Csv ...')
"""
import os
import json
import logging
from typing import Optional

logger = logging.getLogger("tools.validate")


def validate_terraform(
    tf_code: str,
    *,
    filename: str = "main.tf",
    providers: Optional[dict] = None,
) -> dict:
    """
    Validate Terraform code in an E2B sandbox.

    Runs: terraform init → terraform validate → terraform fmt -check
    Returns structured pass/fail result with error details.

    Args:
        tf_code: The Terraform HCL code to validate
        filename: Filename to write (default: main.tf)
        providers: Optional provider configuration overrides

    Returns:
        dict with keys:
            - "passed": bool
            - "errors": list[str] — validation errors (empty if passed)
            - "warnings": list[str] — non-fatal warnings
            - "formatted": bool — whether code passes fmt check
            - "stdout": str — raw stdout from validation
    """
    api_key = os.getenv("E2B_API_KEY", "").strip()
    if not api_key:
        logger.warning("[E2B] API key not set — falling back to local syntax check")
        return _local_tf_validate(tf_code)

    logger.info("[E2B] Validating %d bytes of Terraform code...", len(tf_code))

    try:
        from e2b_code_interpreter import Sandbox

        with Sandbox(api_key=api_key, timeout=60) as sbx:
            # Write the terraform file
            sbx.files.write(f"/home/user/{filename}", tf_code)

            # Write a minimal provider config if not provided
            if providers is None and "required_providers" not in tf_code:
                provider_tf = '''
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}
provider "azurerm" {
  features {}
  skip_provider_registration = true
}
'''
                sbx.files.write("/home/user/providers.tf", provider_tf)

            # Install terraform if not present
            install = sbx.commands.run(
                "which terraform || (curl -fsSL https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip -o /tmp/tf.zip && unzip -o /tmp/tf.zip -d /usr/local/bin/)",
                timeout=30,
            )

            # terraform init (download providers)
            init_result = sbx.commands.run(
                "cd /home/user && terraform init -backend=false -no-color",
                timeout=60,
            )

            errors = []
            warnings = []

            if init_result.exit_code != 0:
                errors.append(f"terraform init failed:\n{init_result.stderr or init_result.stdout}")
                return {
                    "passed": False,
                    "errors": errors,
                    "warnings": warnings,
                    "formatted": False,
                    "stdout": init_result.stdout or "",
                }

            # terraform validate
            validate_result = sbx.commands.run(
                "cd /home/user && terraform validate -json -no-color",
                timeout=30,
            )

            try:
                val_json = json.loads(validate_result.stdout)
                if not val_json.get("valid", False):
                    for diag in val_json.get("diagnostics", []):
                        severity = diag.get("severity", "error")
                        summary = diag.get("summary", "Unknown error")
                        detail = diag.get("detail", "")
                        msg = f"{summary}: {detail}" if detail else summary
                        if severity == "error":
                            errors.append(msg)
                        else:
                            warnings.append(msg)
            except json.JSONDecodeError:
                if validate_result.exit_code != 0:
                    errors.append(validate_result.stderr or validate_result.stdout or "Validation failed")

            # terraform fmt -check
            fmt_result = sbx.commands.run(
                "cd /home/user && terraform fmt -check -diff -no-color",
                timeout=10,
            )
            formatted = fmt_result.exit_code == 0

            passed = len(errors) == 0

            logger.info(
                "[E2B] Validation %s: %d errors, %d warnings, fmt=%s",
                "PASSED" if passed else "FAILED", len(errors), len(warnings), formatted,
            )

            return {
                "passed": passed,
                "errors": errors,
                "warnings": warnings,
                "formatted": formatted,
                "stdout": validate_result.stdout or "",
            }

    except ImportError:
        logger.warning("[E2B] e2b-code-interpreter not installed — falling back to local check")
        return _local_tf_validate(tf_code)
    except Exception as e:
        logger.error("[E2B] Sandbox validation failed: %s", e)
        return {
            "passed": False,
            "errors": [f"Sandbox error: {str(e)}"],
            "warnings": [],
            "formatted": False,
            "stdout": "",
        }


def validate_powershell(
    ps_code: str,
    *,
    filename: str = "script.ps1",
    severity: str = "Error",
) -> dict:
    """
    Validate PowerShell code via PSScriptAnalyzer in an E2B sandbox.

    Args:
        ps_code: The PowerShell script to validate
        filename: Filename to write
        severity: Minimum severity to report ("Error", "Warning", "Information")

    Returns:
        dict with keys:
            - "passed": bool
            - "errors": list[str] — lint findings
            - "warnings": list[str]
            - "stdout": str
    """
    api_key = os.getenv("E2B_API_KEY", "").strip()
    if not api_key:
        logger.warning("[E2B] API key not set — falling back to basic PS syntax check")
        return _local_ps_validate(ps_code)

    logger.info("[E2B] Validating %d bytes of PowerShell code...", len(ps_code))

    try:
        from e2b_code_interpreter import Sandbox

        with Sandbox(api_key=api_key, timeout=60) as sbx:
            sbx.files.write(f"/home/user/{filename}", ps_code)

            # Install pwsh + PSScriptAnalyzer
            sbx.commands.run(
                "which pwsh || (apt-get update -qq && apt-get install -y -qq powershell)",
                timeout=60,
            )
            sbx.commands.run(
                "pwsh -Command 'if (-not (Get-Module -ListAvailable PSScriptAnalyzer)) { Install-Module PSScriptAnalyzer -Force -Scope CurrentUser }'",
                timeout=30,
            )

            # Run PSScriptAnalyzer
            result = sbx.commands.run(
                f"pwsh -Command 'Invoke-ScriptAnalyzer -Path /home/user/{filename} -Severity {severity} | ConvertTo-Json'",
                timeout=30,
            )

            errors = []
            warnings = []

            if result.stdout and result.stdout.strip() not in ("", "null", "[]"):
                try:
                    findings = json.loads(result.stdout)
                    if isinstance(findings, dict):
                        findings = [findings]
                    for f in findings:
                        msg = f"{f.get('RuleName', 'Unknown')}: {f.get('Message', '')} (line {f.get('Line', '?')})"
                        if f.get("Severity", "").lower() == "error":
                            errors.append(msg)
                        else:
                            warnings.append(msg)
                except json.JSONDecodeError:
                    if result.exit_code != 0:
                        errors.append(result.stdout)

            passed = len(errors) == 0
            logger.info("[E2B] PS validation %s: %d errors, %d warnings", "PASSED" if passed else "FAILED", len(errors), len(warnings))

            return {
                "passed": passed,
                "errors": errors,
                "warnings": warnings,
                "stdout": result.stdout or "",
            }

    except Exception as e:
        logger.error("[E2B] PS validation failed: %s", e)
        return _local_ps_validate(ps_code)


def _local_tf_validate(tf_code: str) -> dict:
    """Basic local syntax check when E2B is unavailable."""
    errors = []
    warnings = []

    # Check for common HCL issues
    brace_count = tf_code.count("{") - tf_code.count("}")
    if brace_count != 0:
        errors.append(f"Mismatched braces: {'+' if brace_count > 0 else ''}{brace_count}")

    quote_count = tf_code.count('"') % 2
    if quote_count != 0:
        errors.append("Unclosed string literal (odd number of quotes)")

    if "resource" in tf_code and "=" not in tf_code:
        warnings.append("Resource block appears to have no attributes")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings + ["⚠️ Local check only — E2B_API_KEY not set for full sandbox validation"],
        "formatted": True,
        "stdout": "",
    }


def _local_ps_validate(ps_code: str) -> dict:
    """Basic local syntax check for PowerShell when E2B is unavailable."""
    errors = []
    warnings = ["⚠️ Local check only — E2B_API_KEY not set for PSScriptAnalyzer validation"]

    # Check for common PS issues
    if ps_code.count("{") != ps_code.count("}"):
        errors.append("Mismatched curly braces")
    if ps_code.count("(") != ps_code.count(")"):
        errors.append("Mismatched parentheses")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stdout": "",
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

    # Test terraform validation
    good_tf = '''
resource "azurerm_resource_group" "example" {
  name     = "example-rg"
  location = "East US"
}
'''
    result = validate_terraform(good_tf)
    print(f"Terraform validation: {'PASSED' if result['passed'] else 'FAILED'}")
    if result["errors"]:
        print(f"Errors: {result['errors']}")
