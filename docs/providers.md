# Prompt expansion

Expansion converts a plain request into Ming's structured layout format. The Lab validates the result before starting image generation. Direct mode skips this step and needs no text-model account.

## Configure on the Spark

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set a model name and API key for each provider you want to offer. Restart the container after changing settings. Keys stay on the Spark; the browser receives only provider and model names. Model names are configurable because each provider's catalog changes.

| Provider | Environment variables | API documentation |
| --- | --- | --- |
| OpenAI | `ANTLING_OPENAI_MODEL`, `ANTLING_OPENAI_API_KEY` | [Responses](https://platform.openai.com/docs/api-reference/responses) |
| Claude | `ANTLING_ANTHROPIC_MODEL`, `ANTLING_ANTHROPIC_API_KEY` | [Messages](https://platform.claude.com/docs/en/api/messages/create) |
| Z.ai | `ANTLING_ZAI_MODEL`, `ANTLING_ZAI_API_KEY` | [Chat Completions](https://docs.z.ai/api-reference/llm/chat-completion) |
| DeepSeek | `ANTLING_DEEPSEEK_MODEL`, `ANTLING_DEEPSEEK_API_KEY` | [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) |
| Custom | `ANTLING_COMPAT_MODEL`, `ANTLING_COMPAT_BASE_URL`, optional `ANTLING_COMPAT_API_KEY` | OpenAI-compatible `/chat/completions` |

Only the selected provider receives your prompt. Use direct mode or a local text model if the prompt must stay on your hardware. Expansion can fail if a model does not follow the JSON format; the Lab reports the error and does not start an image job.

## Local or custom endpoint

Set the base URL including the API prefix, for example `http://host.docker.internal:11434/v1`, and the model name served by that endpoint. The Docker host alias reaches the Spark host; the text server must listen on an interface accessible from Docker. Restrict its access to your trusted local network or Docker bridge. Another text model also consumes memory, so leave enough free for image inference.

With an API key, the endpoint must use HTTPS. HTTP is allowed for a keyless local endpoint. Redirects are rejected so credentials and prompts cannot be forwarded to an unexpected URL.

## Optional Codex CLI helper

On a Mac with a signed-in Codex CLI and a copy of this repo, run:

```bash
python3 scripts/prompt_rewriter_bridge.py
```

Keep that terminal open. When you open the Lab at `http://127.0.0.1:8765/`, the dropdown also offers **Codex CLI on this Mac**. The helper uses the CLI's signed-in account, which is separate from an OpenAI API key. Use `MING_CODEX_BIN` to override the executable path and `MING_REWRITER_MODEL` to select a model available to your account.

The helper is optional. Claude support uses the Claude API; it does not use a Claude Code subscription or CLI login.
