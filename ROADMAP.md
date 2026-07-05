# Wingman Clone — Integration Roadmap

## Phase 1: Core Foundation (Weeks 1-2) - COMPLETE

- [x] Architecture document
- [x] BaseTool interface + auto-discovery registry
- [x] Agent orchestrator with tool-calling loop
- [x] Memory system (conversation + durable facts)
- [x] FastAPI endpoints (`/chat`, `/tools`, `/memory`)
- [x] Example tools: get_weather, get_time, calculator
- [x] Test suite

---

## Phase 2: Notion Integration (Weeks 3-4)

### Goal
Allow the agent to read/write Notion pages, databases, and blocks -- enabling task management, knowledge base queries, and note-taking through natural language.

### Implementation Plan

```
src/integrations/notion/
|-- __init__.py
|-- client.py          # Notion API client wrapper
|-- tools.py           # Notion-specific tools (registered via BaseTool)
+-- auth.py            # OAuth2 flow for Notion
```

### Tools to Implement

| Tool Name                | Description                                    | Priority |
|--------------------------|------------------------------------------------|----------|
| `notion_search`          | Search across all Notion pages & databases     | P0       |
| `notion_read_page`       | Read content of a specific page                | P0       |
| `notion_create_page`     | Create a new page in a database                | P0       |
| `notion_update_page`     | Update properties or content of a page         | P1       |
| `notion_query_database`  | Query a database with filters/sorts            | P1       |
| `notion_create_database` | Create a new database                          | P2       |
| `notion_add_block`       | Append blocks (text, todo, etc.) to a page     | P1       |

### Auth Flow

1. User connects Notion via OAuth2 (Notion public integration)
2. Access token stored encrypted in durable memory
3. Token refresh handled transparently by `client.py`

### Example Interaction

```
User: "Add a task to my Notion board: Review Q2 financials by Friday"

Agent:
  1. LLM selects `notion_query_database` -> finds "Tasks" database
  2. LLM selects `notion_create_page` -> creates page with:
     - Title: "Review Q2 financials"
     - Due Date: Friday
     - Status: "To Do"
  3. Returns: "Done! I've added 'Review Q2 financials' to your Tasks board, due Friday."
```

---

## Phase 3: Social Media Integrations (Weeks 5-8)

### 3a. Twitter/X Integration (Week 5-6)

```
src/integrations/twitter/
|-- __init__.py
|-- client.py          # Twitter API v2 client
|-- tools.py           # Twitter tools
+-- auth.py            # OAuth 2.0 PKCE flow
```

#### Tools

| Tool Name              | Description                                | Priority |
|------------------------|--------------------------------------------|----------|
| `twitter_post_tweet`   | Compose and post a tweet                   | P0       |
| `twitter_read_timeline`| Read recent tweets from home timeline      | P0       |
| `twitter_search`       | Search tweets by keyword/hashtag           | P1       |
| `twitter_read_mentions`| Read mentions and replies                  | P1       |
| `twitter_reply`        | Reply to a specific tweet                  | P1       |
| `twitter_schedule_tweet`| Schedule a tweet for later                | P2       |
| `twitter_analytics`    | Get engagement metrics for recent tweets   | P2       |

#### Safety Rails

- **Drafts first**: Agent generates tweet text -> shows to user for approval -> posts only after confirmation.
- **Content policy**: LLM system prompt includes guidelines to avoid posting anything controversial, confidential, or off-brand.
- **Rate awareness**: Respect Twitter API rate limits (post limits, read limits).

### 3b. LinkedIn Integration (Week 6-7)

```
src/integrations/linkedin/
|-- __init__.py
|-- client.py          # LinkedIn API client
|-- tools.py           # LinkedIn tools
+-- auth.py            # OAuth 2.0 3-legged flow
```

#### Tools

| Tool Name                  | Description                              | Priority |
|----------------------------|------------------------------------------|----------|
| `linkedin_create_post`     | Create a text/image post                 | P0       |
| `linkedin_read_feed`       | Read recent feed items                   | P1       |
| `linkedin_read_notifications` | Read notifications                    | P1       |
| `linkedin_send_message`    | Send a direct message                    | P2       |
| `linkedin_search_people`   | Search for people by name/company        | P2       |
| `linkedin_schedule_post`   | Schedule a post for optimal time         | P2       |

### 3c. Instagram Integration (Week 7-8)

```
src/integrations/instagram/
|-- __init__.py
|-- client.py          # Instagram Graph API client
|-- tools.py           # Instagram tools
+-- auth.py            # Facebook OAuth flow
```

#### Tools

| Tool Name                  | Description                              | Priority |
|----------------------------|------------------------------------------|----------|
| `instagram_create_post`    | Create image/carousel post               | P0       |
| `instagram_create_story`   | Create a story                           | P1       |
| `instagram_read_comments`  | Read comments on recent posts            | P1       |
| `instagram_reply_comment`  | Reply to a comment                       | P1       |
| `instagram_analytics`      | Get post/account analytics               | P2       |

---

## Phase 4: Cross-Platform Intelligence (Weeks 9-10)

### Smart Scheduling
- Analyze engagement data across platforms to suggest optimal posting times.
- "Post this to Twitter now and LinkedIn tomorrow at 9am" -- single command.

### Content Adaptation
- User writes one message; agent adapts it per platform:
  - Twitter: concise, hashtags, thread if needed
  - LinkedIn: professional tone, longer form
  - Instagram: caption + suggested image prompt

### Unified Inbox
- Aggregate mentions, comments, DMs across all platforms.
- "What's new across my social media?" -> single summary.

---

## Phase 5: Advanced Features (Weeks 11-16)

| Feature                    | Description                                           |
|----------------------------|-------------------------------------------------------|
| **Scheduled Tasks**        | Cron-like scheduling (daily summaries, reminders)     |
| **Multi-user**             | Support multiple users with isolated memory           |
| **Webhook Receivers**      | Listen for events (new email, calendar change)        |
| **File Processing**        | Analyze uploaded PDFs, images, spreadsheets           |
| **Voice Interface**        | Whisper STT -> Agent -> TTS response                  |
| **Custom Skill Packs**     | Shareable bundles of tools + prompts                  |

---

## Integration Architecture Pattern

Every integration follows the same structure:

```python
# src/integrations/base.py
class BaseIntegration(ABC):
    name: str
    description: str
    
    @abstractmethod
    async def authenticate(self, credentials: dict) -> bool: ...
    
    @abstractmethod
    def get_tools(self) -> list[BaseTool]: ...
    
    @abstractmethod
    async def health_check(self) -> bool: ...
```

This ensures:
- **Consistent auth flow** across all integrations
- **Auto-registration** of integration tools into the Tool Sandbox
- **Health monitoring** so the agent knows which integrations are active
- **Easy testing** with mock implementations
