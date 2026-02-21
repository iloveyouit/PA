"""
Memory Ingest Pipeline — Vectorize markdown files into Pinecone.

Scans configured directories for .md files, chunks them intelligently,
generates embeddings, and upserts to Pinecone for semantic recall.

Supports:
- Obsidian vault (KB articles, notes)
- PA memory files (daily logs, profiles)
- Notion exports (markdown dumps)
- Arbitrary markdown directories

Usage:
    # CLI
    python -m src.memory.ingest --source /path/to/vault
    python -m src.memory.ingest --source memory/  # PA memory files

    # Python
    from src.memory.ingest import ingest_directory, ingest_file
    stats = ingest_directory("/path/to/vault")
"""
import os
import re
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = logging.getLogger("memory.ingest")

# ---------------------------------------------------------------------------
# Chunking config
# ---------------------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 800      # ~800 tokens per chunk (conservative)
DEFAULT_CHUNK_OVERLAP = 100   # overlap for context continuity
MIN_CHUNK_SIZE = 50           # skip tiny chunks


@dataclass
class ChunkResult:
    """A single text chunk with metadata."""
    content: str
    source_file: str
    chunk_index: int
    heading: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def doc_id(self) -> str:
        """Deterministic ID from content + source."""
        raw = f"{self.source_file}::{self.chunk_index}::{self.content[:100]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class IngestStats:
    """Summary of an ingestion run."""
    files_scanned: int = 0
    files_ingested: int = 0
    files_skipped: int = 0
    chunks_created: int = 0
    chunks_upserted: int = 0
    errors: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Chunking logic
# ---------------------------------------------------------------------------
def _chunk_markdown(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    """
    Split markdown text into chunks, respecting heading boundaries.

    Strategy:
    1. Split on ## headings first (section-level chunks)
    2. If a section exceeds chunk_size, split on paragraphs
    3. If a paragraph exceeds chunk_size, split on sentences
    4. Overlap between chunks for context continuity
    """
    if not text or len(text.strip()) < MIN_CHUNK_SIZE:
        return []

    chunks = []
    current_heading = ""

    # Split on ## headings
    sections = re.split(r'^(#{1,3}\s+.+)$', text, flags=re.MULTILINE)

    buffer = ""
    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Check if this is a heading
        if re.match(r'^#{1,3}\s+', section):
            current_heading = section.lstrip('#').strip()
            continue

        # If adding this section would exceed chunk_size, flush buffer
        if len(buffer) + len(section) > chunk_size and buffer:
            chunks.append({"content": buffer.strip(), "heading": current_heading})
            # Keep overlap
            overlap_text = buffer[-chunk_overlap:] if len(buffer) > chunk_overlap else ""
            buffer = overlap_text

        # If the section itself is too large, split on paragraphs
        if len(section) > chunk_size:
            paragraphs = section.split("\n\n")
            for para in paragraphs:
                if len(buffer) + len(para) > chunk_size and buffer:
                    chunks.append({"content": buffer.strip(), "heading": current_heading})
                    overlap_text = buffer[-chunk_overlap:] if len(buffer) > chunk_overlap else ""
                    buffer = overlap_text

                buffer += "\n\n" + para if buffer else para
        else:
            buffer += "\n\n" + section if buffer else section

    # Flush remaining buffer
    if buffer.strip() and len(buffer.strip()) >= MIN_CHUNK_SIZE:
        chunks.append({"content": buffer.strip(), "heading": current_heading})

    return chunks


def _extract_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown if present."""
    meta = {}
    content = text

    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm_block = text[3:end].strip()
            content = text[end + 3:].strip()
            for line in fm_block.split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip()

    return meta, content


# ---------------------------------------------------------------------------
# File ingestion
# ---------------------------------------------------------------------------
def ingest_file(
    filepath: str,
    *,
    source_label: Optional[str] = None,
    extra_metadata: Optional[dict] = None,
) -> list[ChunkResult]:
    """
    Read a single markdown file, chunk it, and return ChunkResults
    ready for embedding and upsert.

    Args:
        filepath: Path to the .md file
        source_label: Label for the source (e.g., "obsidian-vault", "pa-memory")
        extra_metadata: Additional metadata to attach to all chunks

    Returns:
        List of ChunkResult objects
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning("File not found: %s", filepath)
        return []

    if path.suffix.lower() not in (".md", ".markdown", ".txt"):
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.error("Failed to read %s: %s", filepath, e)
        return []

    if len(text.strip()) < MIN_CHUNK_SIZE:
        logger.debug("Skipping %s — too short (%d chars)", filepath, len(text))
        return []

    # Extract frontmatter
    frontmatter, body = _extract_frontmatter(text)

    # Chunk the content
    raw_chunks = _chunk_markdown(body)

    results = []
    for i, chunk in enumerate(raw_chunks):
        meta = {
            "source": source_label or "unknown",
            "source_file": str(path.name),
            "source_path": str(path),
            "heading": chunk.get("heading", ""),
            "chunk_index": i,
            "file_modified": datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        }

        # Add frontmatter fields
        if frontmatter:
            meta["frontmatter"] = str(frontmatter)[:500]

        # Add extra metadata
        if extra_metadata:
            meta.update(extra_metadata)

        results.append(ChunkResult(
            content=chunk["content"],
            source_file=str(path),
            chunk_index=i,
            heading=chunk.get("heading", ""),
            metadata=meta,
        ))

    logger.debug("Chunked %s → %d chunks", path.name, len(results))
    return results


# ---------------------------------------------------------------------------
# Directory ingestion
# ---------------------------------------------------------------------------
def ingest_directory(
    directory: str,
    *,
    source_label: Optional[str] = None,
    recursive: bool = True,
    exclude_patterns: Optional[list[str]] = None,
    dry_run: bool = False,
) -> IngestStats:
    """
    Scan a directory for .md files, chunk them, embed them, and upsert to Pinecone.

    Args:
        directory: Path to scan
        source_label: Label for the source (auto-detected if not provided)
        recursive: Whether to recurse into subdirectories
        exclude_patterns: Glob patterns to exclude (e.g., [".obsidian", "templates"])
        dry_run: If True, chunk files but don't embed/upsert (for testing)

    Returns:
        IngestStats summary
    """
    stats = IngestStats()
    dir_path = Path(directory).resolve()

    if not dir_path.exists():
        logger.error("Directory not found: %s", directory)
        stats.errors.append(f"Directory not found: {directory}")
        return stats

    # Auto-detect source label
    if source_label is None:
        if "vault" in str(dir_path).lower() or "obsidian" in str(dir_path).lower():
            source_label = "obsidian-vault"
        elif "memory" in str(dir_path).lower():
            source_label = "pa-memory"
        elif "notion" in str(dir_path).lower():
            source_label = "notion-export"
        else:
            source_label = dir_path.name

    # Default exclusions
    exclude = set(exclude_patterns or [])
    exclude.update([".obsidian", ".git", "node_modules", "__pycache__", ".trash"])

    # Collect markdown files
    pattern = "**/*.md" if recursive else "*.md"
    md_files = sorted(dir_path.glob(pattern))

    # Filter exclusions
    filtered_files = []
    for f in md_files:
        skip = False
        for exc in exclude:
            if exc in str(f):
                skip = True
                break
        if not skip:
            filtered_files.append(f)

    logger.info(
        "📂 Scanning %s: found %d markdown files (%d after exclusions)",
        dir_path, len(md_files), len(filtered_files),
    )

    # Chunk all files
    all_chunks: list[ChunkResult] = []
    for f in filtered_files:
        stats.files_scanned += 1
        chunks = ingest_file(str(f), source_label=source_label)
        if chunks:
            all_chunks.extend(chunks)
            stats.files_ingested += 1
        else:
            stats.files_skipped += 1

    stats.chunks_created = len(all_chunks)
    logger.info(
        "📝 Chunked %d files → %d chunks (skipped %d)",
        stats.files_ingested, stats.chunks_created, stats.files_skipped,
    )

    if dry_run:
        logger.info("🔍 Dry run — skipping embed/upsert")
        return stats

    # Upsert to Pinecone
    if all_chunks:
        try:
            from src.tools.query_pinecone import bulk_upsert

            documents = [
                {
                    "id": chunk.doc_id,
                    "content": chunk.content,
                    "metadata": chunk.metadata,
                }
                for chunk in all_chunks
            ]

            upserted = bulk_upsert(documents, batch_size=50)
            stats.chunks_upserted = upserted
            logger.info("✅ Upserted %d/%d chunks to Pinecone", upserted, len(documents))

        except Exception as e:
            logger.error("❌ Pinecone upsert failed: %s", e)
            stats.errors.append(f"Upsert failed: {str(e)}")

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    """CLI entry point for ingestion."""
    import argparse
    from rich.console import Console
    from rich.table import Table

    parser = argparse.ArgumentParser(
        description="Ingest markdown files into Pinecone vector memory",
    )
    parser.add_argument(
        "--source", "-s",
        required=True,
        help="Directory to scan for .md files",
    )
    parser.add_argument(
        "--label", "-l",
        default=None,
        help="Source label (auto-detected if not provided)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't recurse into subdirectories",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=None,
        help="Patterns to exclude",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk files but don't embed/upsert",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    console = Console()
    console.print(f"\n🧠 [bold]Memory Ingest Pipeline[/bold]")
    console.print(f"Source: {args.source}")
    if args.dry_run:
        console.print("[yellow]DRY RUN — no vectors will be stored[/yellow]")

    stats = ingest_directory(
        args.source,
        source_label=args.label,
        recursive=not args.no_recursive,
        exclude_patterns=args.exclude,
        dry_run=args.dry_run,
    )

    # Print results
    table = Table(title="Ingest Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Files scanned", str(stats.files_scanned))
    table.add_row("Files ingested", str(stats.files_ingested))
    table.add_row("Files skipped", str(stats.files_skipped))
    table.add_row("Chunks created", str(stats.chunks_created))
    table.add_row("Chunks upserted", str(stats.chunks_upserted))
    if stats.errors:
        table.add_row("Errors", str(len(stats.errors)))
    console.print(table)

    if stats.errors:
        for err in stats.errors:
            console.print(f"  [red]✗ {err}[/red]")


if __name__ == "__main__":
    main()
