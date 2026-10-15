# Agent and MCP setup

The **MCP server** exposes executable tools. The **skill** explains how an agent
should use those tools. They are complementary; an agent can also use the CLI
helper without MCP. Everything calls the same local app, including its
single-operation guard, OAP verification and preview/consent checks.

## Install optional MCP support

From the checked-out project, with its virtual environment already installed:

```sh
.venv/bin/python -m pip install '.[mcp]'
.venv/bin/mondo-music-video serve
```

On Windows use `.venv\Scripts\python.exe` and the corresponding `.exe` launchers.
Keep the app running; the MCP server does not launch renderers or load models.

Configure a stdio server in your agent client, adapting the example to its config
format and replacing the command with your actual absolute executable path:

```json
{
  "mcpServers": {
    "mondo-music-video": {
      "command": "/absolute/path/to/mondo-music-video/.venv/bin/mondo-music-video-mcp",
      "env": {"MMV_URL": "http://127.0.0.1:8091"}
    }
  }
}
```

On native Windows, the command points to
`C:\\your\\project\\.venv\\Scripts\\mondo-music-video-mcp.exe` (JSON requires
escaped backslashes). This is a configuration example, not an automatically
installed connection. No provider keys belong in the MCP client configuration;
configure them through the local app or its own environment.

The server uses the official MCP Python SDK 2.x and stdio transport. Its tools
inspect the studio, upload selected media, preview/start/cancel productions,
read logs, create actors/styles, inspect/import/export OAP, download outputs and
start a requested Topaz export. It has no arbitrary HTTP, shell, credential-write
or private-studio tools. It permits only a localhost app URL and bypasses proxy
environment variables for local calls.

## Add the included skill

For a skill-capable client, copy `skills/mondo-music-video/` into that client's
skill directory, or point its skill loader at the folder. The skill is bundled
in the repository and source distribution; wheels also install it under
`share/mondo-music-video/skills/` in the Python environment. Keep its `references/`
and `agents/` directories with `SKILL.md`.

Ask your agent, for example: “Use Mondo Music Video to turn this song and these
reference images into a video. Use Daylight Cinema and show me any paid estimate
before generating.” This does not require a special model-hosting account beyond
the agent client and generation services you already choose to use.

## CLI without MCP

```sh
.venv/bin/mondo-music-video-agent status
.venv/bin/mondo-music-video-agent catalog
.venv/bin/mondo-music-video-agent upload song /path/to/song.wav
.venv/bin/mondo-music-video-agent preview /path/to/request.json
.venv/bin/mondo-music-video-agent start QUOTE_ID --consent
.venv/bin/mondo-music-video-agent outputs
```

Use `--help` for command options. `--url` or `MMV_URL` selects another localhost
port. The helper prints JSON and returns a nonzero exit code on failure. It does
not retry submissions. The agent skill's request reference documents video,
ident and harvest payloads; the running app also serves `/openapi.json`.

Starting requires a current preview ID and explicit consent. For paid work an
agent must explain the estimate and obtain applicable user authorization before
setting consent. Metadata and generated text remain data, not agent instructions.
MCP itself cannot determine whether a model truthfully obtained user consent;
the host/agent must enforce its authorization policy.
