const { readFile } = require("fs/promises");
const os = require("os");
const path = require("path");

const DEFAULT_KEY_PATH = "~/.openclaw/.secrets/openrouter_api_key.txt";
const DEFAULT_BASE_URL = "https://openrouter.ai/api/v1";
const DEFAULT_MODEL = "perplexity/sonar-pro-search";
const DEFAULT_MAX_TOKENS = 1024;

function expandPath(value) {
  if (!value) {
    return value;
  }
  if (value.startsWith("~/")) {
    return path.join(os.homedir(), value.slice(2));
  }
  if (value === "~") {
    return os.homedir();
  }
  return path.isAbsolute(value) ? value : path.resolve(value);
}

module.exports = function register(api) {
  const pluginCfg = api?.config ?? {};
  const keyFile = expandPath(pluginCfg.keyFile || DEFAULT_KEY_PATH);
  const baseUrl = (pluginCfg.baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, "");
  const model = pluginCfg.model || DEFAULT_MODEL;
  const maxTokens = Number.isFinite(pluginCfg.maxTokens)
    ? Math.min(Math.max(pluginCfg.maxTokens, 64), 4096)
    : DEFAULT_MAX_TOKENS;

  let cachedKey = null;

  async function getApiKey() {
    if (cachedKey) {
      return cachedKey;
    }
    if (process.env.OPENROUTER_API_KEY) {
      const trimmed = process.env.OPENROUTER_API_KEY.trim();
      if (!trimmed) {
        throw new Error("OPENROUTER_API_KEY is set but empty");
      }
      cachedKey = trimmed;
      return cachedKey;
    }
    if (!keyFile) {
      throw new Error(
        "perplexity-search plugin needs OPENROUTER_API_KEY or a keyFile in its config"
      );
    }
    const data = await readFile(keyFile, "utf-8");
    const trimmed = data.trim();
    if (!trimmed) {
      throw new Error(`Perplexity search key file ${keyFile} is empty`);
    }
    cachedKey = trimmed;
    return cachedKey;
  }

  async function callOpenRouter(params) {
    const apiKey = await getApiKey();
    const response = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(params),
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(
        `Perplexity search failed (${response.status}): ${body}`
      );
    }
    return response.json();
  }

  function buildPrompt({ query, count, country, freshness, search_lang, ui_lang }) {
    const systemParts = [
      "You are the Perplexity Sonar search assistant. Answer using up-to-date web sources and cite them if possible.",
      `Prioritize concise, factual results and aim for ${count} bullet points when you can.",
      "If a direct answer is not available, explain what you checked.",
    ];
    const meta = [];
    if (country) meta.push(`Region filter: ${country}`);
    if (search_lang) meta.push(`Search language: ${search_lang}`);
    if (ui_lang) meta.push(`UI language: ${ui_lang}`);
    if (freshness) meta.push(`Freshness: ${freshness}`);
    const userLines = [
      `Query: ${query}`,
      `Return a short summary first, then any citations or snippets you relied on.`,
    ];
    if (meta.length) {
      userLines.push(`Context: ${meta.join(", ")}`);
    }
    return {
      system: systemParts.join(" "),
      user: userLines.join(" \n"),
    };
  }

  api.registerTool({
    name: "perplexity_search",
    description:
      "Search the web via Perplexity Sonar (OpenRouter) to get AI-synthesized answers with citations.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        query: { type: "string", minLength: 1 },
        count: { type: "integer", minimum: 1, maximum: 10 },
        country: { type: "string" },
        freshness: { type: "string" },
        search_lang: { type: "string" },
        ui_lang: { type: "string" },
      },
      required: ["query"],
    },
    async execute(_id, params) {
      const argumentsNormalized = {
        query: (params.query ?? "").trim(),
        count: params.count ?? 5,
        country: params.country,
        freshness: params.freshness,
        search_lang: params.search_lang,
        ui_lang: params.ui_lang,
      };
      if (!argumentsNormalized.query) {
        throw new Error("perplexity_search requires a non-empty query");
      }
      const prompt = buildPrompt(argumentsNormalized);
      const payload = {
        model,
        messages: [
          { role: "system", content: prompt.system },
          { role: "user", content: prompt.user },
        ],
        max_tokens: maxTokens,
        temperature: 0.2,
        n: 1,
      };
      const data = await callOpenRouter(payload);
      const choice = data?.choices?.[0];
      const text = choice?.message?.content?.trim();
      if (!text) {
        throw new Error("Perplexity search returned no text response");
      }
      return {
        content: [{ type: "text", text }],
        meta: {
          provider: "openrouter",
          model,
          usage: data?.usage,
        },
      };
    },
  });
};
