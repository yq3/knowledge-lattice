# MCP 接入指南（Agent 侧）

> 面向：要把自己的 agent 接到 knowledge-lattice 的工程师。
> 适用：`LATTICE_AUTH_MODE=local`（D25 内置账号 + D26 agent key）。
> `sso` 形态仍走 D18 委托 token / 可信子系统，见 §9。
> 事实来源：`src/knowledge_lattice/mcp/server.py`、`app.py`、`domain/agent_keys.py`、
> `tests/test_agent_key_e2e.py`（客户端示例与实际认证路径一致）。

## 1. 最短路径：三样东西

| 你需要 | 值 / 从哪来 |
|---|---|
| **MCP 端点** | `http://<host>:<port>/mcp`（默认本机 `http://127.0.0.1:8000/mcp`） |
| **凭据** | local 形态：**Agent Key**（`lka_...`），在网页「Agent 密钥」签发；见 §2 |
| **客户端能力** | 支持 **Streamable HTTP** 传输 + 自定义请求头（`Authorization`） |

连接就是一个 URL + 一个 Bearer 头：

```text
URL:    http://127.0.0.1:8000/mcp
Header: Authorization: Bearer lka_xxxxxxxx...
```

> **组织上下文不用配**：agent key 已绑定一个组织，服务端从 key 读取；客户端**不要**
> 再传 `X-Org-Id`（若客户端框架强制传，值必须等于 key 绑定组织，否则 400）。
>
> **这个服务只提供 Streamable HTTP**，不是 stdio，也不提供 SSE 端点；只支持 stdio 的
> 客户端需要用桥接（§4.6）。

## 2. 签发 Agent Key

### 2.1 网页（推荐）

local 登录 → 左侧「管理 → **Agent 密钥**」→「＋ 新建 Agent Key」→
选择本组织 active 成员 → 填 label（agent 名，如 `tax-agent-a`）→ 签发。

- 明文 `lka_...` **只显示一次**，立即复制；刷新/切组织后不可再查看；
- 每把 key 绑定 `(组织, 用户, label)`：**一个 agent 一把**，审计按 label 区分；
- key 继承归属成员的全部权限（无 key 级 scope，G-35）——建议给 agent 建专用低权成员账号。

### 2.2 REST（自动化签发）

用有权限的**会话 token**（不是 agent key）调管理面：

```bash
curl -s -X POST http://127.0.0.1:8000/api/orgs/<org>/agent-keys \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"user_id":"u_xxx","label":"tax-agent-a"}'
```

响应中的 `key` 是唯一一次明文；`expires_at` 为 `null`（永不过期，只能撤销）。
权限：本组织 `org_admin`，或 `sysadmin` 豁免；目标必须是该组织 active 成员。

## 3. 本地 / 远程访问

- 当前示例服务只绑 `127.0.0.1`：**同一台机器**上的 agent 才能用 `127.0.0.1:8000`。
- agent 在别的机器上：服务需以 `--host 0.0.0.0`（或内网网卡 IP）启动，放行端口，
  并把 URL 换成服务机 IP/域名。
- **非 loopback 必须上 TLS**（反向代理 / 内网网关）——agent key 是长期 Bearer，
  明文 HTTP 只允许受信内网 demo。
- MCP 调用是 agent 服务端发起的 HTTP，不涉及浏览器 CORS。

## 4. 客户端配置

### 4.1 Claude Code（CLI，已按 `claude mcp add --help` 核对）

```bash
claude mcp add --transport http knowledge-lattice \
  http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer lka_xxxxxxxx..."

# 查看 / 删除
claude mcp list
claude mcp remove knowledge-lattice
```

`--scope user` 可让配置跨项目生效（默认 local）。`--header` 可重复，用于额外头。

### 4.2 Claude Desktop（配置文件）

> 版本差异：新版支持 remote MCP（`type: http` + `headers`）；旧版只支持 stdio，
> 用 §4.6 的 `mcp-remote` 桥接。改完重启 Claude Desktop。

macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
Windows：`%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "knowledge-lattice": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer lka_xxxxxxxx..."
      }
    }
  }
}
```

### 4.3 Cursor

项目级 `.cursor/mcp.json` 或用户级 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "knowledge-lattice": {
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer lka_xxxxxxxx..."
      }
    }
  }
}
```

（以所用 Cursor 版本的 remote MCP 支持为准；同样要求自定义 header。）

### 4.4 Python（FastMCP 客户端，本仓测试同款）

```python
import asyncio
import json

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

URL = "http://127.0.0.1:8000/mcp"
KEY = "lka_xxxxxxxx..."  # 从环境变量/密钥管理读取，不要写进代码库


async def main() -> None:
    transport = StreamableHttpTransport(
        url=URL,
        headers={"Authorization": f"Bearer {KEY}"},
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        print("tools:", [t.name for t in tools])

        result = await client.call_tool(
            "search", {"query": "增值税留抵退税", "top_k": 5}
        )
        payload = json.loads(result.content[0].text)
        print(json.dumps(payload, ensure_ascii=False, indent=2))


asyncio.run(main())
```

本仓提供一键冒烟脚本（只读，不打印 key）：

```bash
export LATTICE_MCP_KEY="lka_xxxxxxxx..."
uv run python scripts/mcp_smoke.py \
  --url http://127.0.0.1:8000/mcp \
  --query "增值税留抵退税"
```

### 4.5 LangChain / deepagents（`langchain-mcp-adapters`）

deepagents 是 LangChain 系；用 `langchain-mcp-adapters` 的
`MultiServerMCPClient` 接入（接口以所用版本为准）：

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "knowledge-lattice": {
        "transport": "streamable_http",
        "url": "http://127.0.0.1:8000/mcp",
        "headers": {"Authorization": "Bearer lka_xxxxxxxx..."},
    }
})
tools = await client.get_tools()
# 把 tools 交给 agent；工具名见 §5
```

### 4.6 只支持 stdio 的客户端（桥接）

用 `mcp-remote` 把远端 Streamable HTTP 桥成本地 stdio（需要 Node/npx）：

```json
{
  "mcpServers": {
    "knowledge-lattice": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://127.0.0.1:8000/mcp",
        "--header", "Authorization: Bearer lka_xxxxxxxx..."
      ]
    }
  }
}
```

> key 会出现在客户端配置进程参数里；确保该配置仅本机可读。内网无法访问 npm 时，
> 改用支持 HTTP 的客户端或自写一个薄 stdio 代理。

### 4.7 手工验证工具面

MCP Inspector（需要 Node）：

```bash
npx -y @modelcontextprotocol/inspector
```

选择 **Streamable HTTP**，URL 填 `http://127.0.0.1:8000/mcp`，添加请求头
`Authorization: Bearer lka_...`，即可看工具列表并逐个调用。

## 5. 工具清单（同一 server，两组工具）

| 工具 | 主要参数 | 用途 |
|---|---|---|
| `search` | `query`, `top_k=8`, `datasets?`, `doc_filter?`, `entities?`, `auto_entities?` | 权限内混合检索（BM25+向量+rerank+实体召回），返回带 `chunk_id` 的块与 `notice` |
| `fetch` | `chunk_id`, `window=2` | 取块前后文；旧版本块带 `replaced_by` 提示 |
| `upload` | `upload_id`, `dataset`, `dimensions`, `doc_id?`, `title?` | 上传三步的③，消费 REST 预签发的 `upload_id`（见 §7） |
| `list_documents` | `datasets?`, `active_status?`, `limit=50` | 权限内知识库/文档清单（按 ACL 统计） |
| `annotate` | `text`, `context_entities?`, `prefer_types?`, `fuzzy=false` | 业务术语识别（AC 精确/别名/上下文/模糊） |
| `get_entity` | `id?`, `key?`, `expand?`, `depth=1`, `fanout_limit=50`, `include?` | 实体详情 + 类型化关系展开 |
| `search_entities` | `q`, `types?`, `top_k=10` | 实体检索（别名/前缀/拼音/名称/向量） |
| `describe_table` | `table`, `columns?` | 表/列详情透传（元数据系统不可用返回 degraded） |

注意：

- `org` / `permissions` 不是 agent 可填参数；工具签名里即使出现也会被忽略并记审计（D18/FR-4）。
- 组织来自 key（或 sso 委托 token 的 org claim / `X-Org-Id`）；每次调用一个组织。
- 服务端工具超时 60s（`LATTICE_MCP_TIMEOUT_S`）。

`search` 的最小返回形态：

```json
{
  "results": [
    {"chunk_id": "chk_...", "doc_id": "doc_...", "title": "...", "text": "..."}
  ],
  "notice": {"vector_pending": false, "degraded": []}
}
```

## 6. 组织与权限规则（必须理解）

- agent key 绑定一个组织：`org_claim=key.org_id`。客户端**不用传** `X-Org-Id`；
  传了且与 key 组织不一致 → `400`。
- 每次调用仍走该用户的**成员关系 + 维度 ACL**；key 不绕过 ACL。
- 组织停用 → `403`；成员关系过期/移除 → `403 membership_denied`。
- 一个用户属于多个组织时：**每个组织各签一把 key**（或每次用该组织的 key）。
- REST 的 org 路径端点：key 绑 A 调 B → `403 org_mismatch`（sysadmin 的 key 同受限）；
  非路径端点的 org 由 key claim 决定。
- sso 形态：用 D18 委托 token（`sub`=用户、`act`=agent、`org` claim 或 `X-Org-Id`）；
  local agent key 在 sso 形态**不可用**（管理端点 404、认证 401）。

## 7. 上传（三步，agent 侧）

MCP 的 `upload` 只收不透明 `upload_id`，字节必须先用 **同一把 key** 走 REST：

```bash
# ① 声明并拿 upload_id（同一把 agent key）
curl -s -X POST http://127.0.0.1:8000/api/uploads \
  -H "Authorization: Bearer lka_xxxxxxxx..." \
  -H 'content-type: application/json' \
  -d '{"filename":"vat.html","size":1234,"sha256":"<64位小写hex>","content_type":"text/html"}'

# ② PUT 字节到返回的 upload_url（同一把 key）
curl -s -X PUT http://127.0.0.1:8000/api/uploads/<upload_id> \
  -H "Authorization: Bearer lka_xxxxxxxx..." \
  --data-binary @vat.html

# ③ MCP tool: upload(upload_id=..., dataset=..., dimensions={...}, title=...)
```

- 凭证绑定 `sub + org + 服务身份(act=key label)`；换一把 key 消费同一 `upload_id` →
  三要素不匹配 403；
- 单次消费：③ 成功后 `upload_id` 置 consumed，重试 409；失败不置已用、可重传；
- `dataset` 必须存在，`dimensions` 按该库维度填；写路径同样做 ACL 校验。

## 8. 排错

认证/组织错误通常以**工具错误文本**返回（不是 HTTP 401），客户端会显示为 tool error：

| 现象 | 原因 / 处理 |
|---|---|
| `401: missing Bearer token` | 没带 `Authorization` 头 |
| `401: invalid agent key` | key 错误、不是本实例签发、或实例数据目录不对 |
| `401: agent key revoked` | 已被撤销；重新签发 |
| `401: agent key 仅 local 形态可用` | 服务是 sso 形态；改用 D18 委托 token |
| `401: local session token 不能用于 MCP` | 把网页登录 session 当 key 用了；去「Agent 密钥」签 key |
| `400: org ... 不一致` | 客户端多传了 `X-Org-Id` 且与 key 组织不同；删掉或改对 |
| `403: org disabled` | 组织已停用；`PATCH /api/orgs/{org}` 恢复（sysadmin） |
| `403: ... membership_denied` | 该用户不是组织 active 成员/成员过期 |
| 空结果 / `404`（实体/fetch） | 多半是 ACL/无数据，不是认证；用 `list_documents` 看可见面 |
| 连接被拒 / 超时 | 服务只绑 127.0.0.1、端口/防火墙、agent 在别的机器；改为可达地址/`--host` |
| 工具 60s 超时 | 查询过重或后端慢；缩小 `top_k`/措辞，或看服务端日志 |
| 客户端没有 `headers` 选项 | 客户端只支持 stdio → §4.6 桥接，或换客户端/SDK |

## 9. 与 sso 形态的关系

- 本文的 agent key 是 **local/POC 形态**的长期用户凭据：永不过期、无 key 级 scope、
  无自动轮转（G-35），靠“每 agent 一把 + 可撤销 + 审计 `act`”治理。
- 企业生产目标形态是 **sso**：agent 从 IdP 换短时委托 token（`sub`=用户、`act`=agent），
  或走可信子系统（服务凭证 + `X-On-Behalf-Of` + 用户在场证据）；见 D18 与 RUNBOOK。
- 切换 `LATTICE_AUTH_MODE=sso` 后：agent key 认证 401、管理端点 404，需要切换到
  委托/可信凭据。

## 10. 安全清单

- key 视同口令：不写代码库、不进日志、不贴群；配置仅本机可读。
- **一 agent 一 key**（label 进审计 `act`）；不要多个 agent 共用一把。
- 给 agent 建专用低权成员账号（key 继承用户全部权限，无 scope）。
- 泄露立即在「Agent 密钥」撤销（即时 401），再签发新的。
- 非本机访问必须 TLS；不要把 8000 明文端口暴露到公网。
- 服务端审计：`agent_key.created`/`agent_key.revoked` + 查询事件
  `act`/`via=agent_key`/`entry=mcp|rest`；可用它按 agent 追查。

## 11. 参考

- 端点与工具实现：`src/knowledge_lattice/mcp/server.py`、`app.py`
- 认证：`src/knowledge_lattice/domain/agent_keys.py`；D18 委托/可信见 `docs/design.md` §5.5
- 签发/撤销运维：`RUNBOOK.md` §1.ac
- 用例：`tests/test_agent_key_e2e.py`、`tests/test_agent_key_api.py`
- 已知缺口：`docs/known-gaps.md` G-35
