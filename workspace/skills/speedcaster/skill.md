---
name: speedcaster
description: Process YouTube videos and podcasts to extract transcripts and generate comprehensive, structured summaries in Traditional Chinese. Automatically formats output for Obsidian vault integration.
---

# Speedcaster - YouTube & Podcast Processor

Extracts transcripts from YouTube videos and podcasts, then generates comprehensive summaries formatted for knowledge management in Obsidian.

## When to Use This Skill

Use this skill when the user:
- Provides a YouTube URL or video ID
- Provides a podcast link or transcript
- Uses `@speedcaster` mention
- Asks to summarize, transcribe, or analyze video/podcast content
- Wants to save video insights to their Obsidian vault

## Step-by-Step Process

### Step 1: Extract Transcript

> **⚠️ IMPORTANT:** Never use WebFetch on YouTube URLs - it always fails. Use the transcript script instead and infer all metadata from the transcript content.

1. **Identify the input type:**
   - YouTube URL (https://youtube.com/watch?v=...)
   - YouTube short URL (https://youtu.be/...)
   - YouTube shorts (https://youtube.com/shorts/...)
   - Direct video ID (11 characters)
   - Podcast URL
   - Existing transcript text

2. **For YouTube videos, use the youtube-transcript script:**
   ```bash
   bash ~/.claude/skills/speedcaster/scripts/youtube-transcript.sh "<YOUTUBE_URL>"
   ```

   This script:
   - Supports multiple URL formats
   - Automatically falls back to Chinese if English unavailable
   - Returns SRT format with timestamps
   - Handles translation if needed

3. **For podcasts:**
   - If URL provided, use WebFetch to get the page
   - Look for transcript sections or links
   - Extract transcript text

4. **Handle errors gracefully:**
   - If transcript unavailable, inform the user
   - If YouTube is blocking, suggest alternatives
   - If video has no captions, explain limitations

### Step 2: Analyze and Summarize Content

After obtaining the transcript, generate a comprehensive summary in **Traditional Chinese (繁體中文)** with the following structure:

#### Output Format Template:

```markdown
# [影片標題]

## TL;DR
[120 字元以內的精簡摘要]

## 主題分析

### 1. [主題一標題]
**重點摘要：** [簡短說明]

**詳細內容：**
- [要點 1]
- [要點 2]
- [要點 3]

**時間戳記：** [如果有的話，列出相關時間點]

---

### 2. [主題二標題]
**重點摘要：** [簡短說明]

**詳細內容：**
- [要點 1]
- [要點 2]

**時間戳記：** [相關時間點]

---

[重複其他主題，建議 3-8 個主要主題]

## 問答精華

**Q: [常見問題 1]**
A: [回答]

**Q: [常見問題 2]**
A: [回答]

[至少 3-5 個 Q&A]

## Metadata

- **影片來源：** [YouTube URL]
- **影片時長：** [如果知道的話]
- **講者：** [如果有提到]
- **主題標籤：** #[topic1] #[topic2] #[topic3]
- **處理日期：** [YYYY-MM-DD]

---

## For Obsidian Integration

**建議標題：** `[簡短描述性標題]`

**建議 Frontmatter：**
```yaml
---
type: video-summary
source: youtube
url: [YOUTUBE_URL]
created: YYYY-MM-DD
modified: YYYY-MM-DD
tags: [type/video, topic/[主題], area/[領域]]
status: processed
---
```

**建議存放位置：**
- 如果是 AI/技術主題：`02_Areas/area-research-ai/[子分類]/`
- 如果是創業/管理主題：`02_Areas/area-growth/` 或 `02_Areas/area-people-ops/`
- 如果是工具教學：`03_Resources/tools/`
- 不確定時先放：`00_Inbox/` (週五 16:00 處理時分類)

**連結建議：**
- 處理時記得在每週五 16:00 的 Weekly Review 時連結到對應的 MOC
- 如果內容與現有專案相關，連結到專案 MOC
```

### Step 3: Analysis Guidelines

When analyzing content, focus on:

1. **Technical Accuracy:**
   - Extract exact terminology and concepts
   - Preserve technical details (code snippets, commands, APIs)
   - Note version numbers, tool names, framework details

2. **Actionable Insights:**
   - Highlight "how-to" steps
   - Extract best practices and patterns
   - Note pitfalls and common mistakes mentioned

3. **Context for Knowledge Management:**
   - Identify connections to existing knowledge areas
   - Suggest relevant tags based on content
   - Note related topics for cross-linking

4. **Traditional Chinese Style:**
   - Use 繁體中文 (Traditional Chinese) for all summaries
   - Use technical terms in English when appropriate (e.g., "API", "framework")
   - Format should be clear and scannable

### Step 4: Quality Checks

Before delivering the summary:

1. **Completeness:**
   - TL;DR is under 120 characters
   - At least 3 main topic sections
   - At least 3-5 Q&A items
   - All metadata fields filled

2. **Obsidian Compatibility:**
   - Valid YAML frontmatter
   - Proper tag format (#tag-name)
   - Suggested wikilinks use [[notation]]

3. **Language Quality:**
   - All content in Traditional Chinese (except technical terms)
   - No translation artifacts
   - Natural, readable Chinese

## Important Patterns

### Transcript Processing

**For SRT format transcripts:**
- Parse timestamps and text
- Group by semantic segments (not just subtitle breaks)
- Merge fragmented sentences
- Create coherent paragraphs

**Topic Segmentation:**
- Group content by major theme shifts
- Use speaker changes as potential segment boundaries
- Aim for 3-8 main topics per video (depending on length)
- Each topic should be substantial (not just 1-2 sentences)

### Video Metadata Extraction

**IMPORTANT: Do NOT use WebFetch for YouTube URLs** - it will always fail. Instead, extract metadata from:
- Video title: Infer from transcript content (intro, host mentions, etc.)
- Speaker names: Extract from transcript context
- Duration: Calculate from last SRT timestamp
- Channel/Show name: Often mentioned in intro

All metadata should be inferred from the transcript itself, not fetched from YouTube.

### Handling Different Content Types

**Technical Tutorials:**
- Extract step-by-step instructions
- Note command examples
- Highlight configuration details
- Preserve code snippets

**Interviews/Discussions:**
- Identify key speakers
- Extract main arguments/viewpoints
- Note interesting quotes
- Capture debate points

**Conference Talks:**
- Highlight key insights
- Extract slides/diagram descriptions
- Note Q&A section separately
- Identify research references

## Examples

### Example 1: Technical Deep Dive

**Input:**
```
User: @speedcaster https://www.youtube.com/watch?v=6_BcCthVvb8
```

**Process:**
1. Extract transcript using script
2. Identify it's about "Context Engineering for AI Agents"
3. Generate Traditional Chinese summary with technical terms preserved
4. Suggest tags: #type/video #topic/ai #topic/agents #area/research-ai
5. Recommend location: `02_Areas/area-research-ai/agents/`

### Example 2: Startup/Business Content

**Input:**
```
User: Summarize this video about growth strategies: https://youtu.be/xyz123
```

**Process:**
1. Extract transcript
2. Focus on actionable growth tactics
3. Create Q&A around common growth questions
4. Suggest tags: #type/video #topic/growth #area/startup
5. Recommend location: `02_Areas/area-growth/`

## Tools & Scripts

### Available Scripts

**youtube-transcript.sh**
- Location: `~/.claude/skills/speedcaster/scripts/youtube-transcript.sh`
- Usage: `bash ~/.claude/skills/speedcaster/scripts/youtube-transcript.sh "<URL>"`
- Returns: SRT format with timestamps
- Features: Auto language fallback, translation support

### Built-in Tools

- `Bash` - Execute transcript script
- `WebFetch` - Fetch podcast pages ONLY (NOT for YouTube - always fails)
- `Read` - Read existing transcript files

**Note:** YouTube URLs cannot be fetched via WebFetch. Always use the transcript script and infer metadata from the transcript content.

## Error Handling

Common errors and solutions:

**"Could not extract valid YouTube video ID"**
- Verify URL format
- Try direct video ID if URL parsing fails
- Check for URL encoding issues

**"No transcripts available"**
- Inform user that video has no captions
- Suggest they check if auto-captions are disabled
- Offer to work with manual transcript if provided

**"YouTube is blocking requests"**
- This may happen with frequent requests
- Suggest waiting a few minutes
- Alternative: user can download transcript manually

## Tips

- **Never WebFetch YouTube URLs** - always use the transcript script and infer metadata from content
- Always use Traditional Chinese (繁體中文) for summaries
- Preserve English technical terms (API, framework names, etc.)
- Include timestamps when available from SRT format
- Focus on actionable insights over literal transcription
- Suggest appropriate tags based on content themes
- Consider the user's Obsidian vault structure (PARA method)
- If video is very long (>60min), focus on key segments
- For AI/tech content, be precise with terminology
- Create Q&A from natural questions viewers might have
- Group related points together for better readability
