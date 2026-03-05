# Speedcaster Skill

YouTube 與 Podcast 轉錄與摘要生成器，專為 Obsidian vault 知識管理優化。

## 功能

- 🎥 從 YouTube 影片提取字幕（支援多種語言與自動翻譯）
- 📝 生成繁體中文結構化摘要
- 🏷️ 自動建議 tags 與 Obsidian vault 存放位置
- ⏱️ 包含時間戳記的主題分段
- ❓ 自動生成 Q&A 精華
- 📋 提供 YAML frontmatter 建議

## 使用方式

### 方法 1: 直接在對話中使用（推薦）

```
你: 幫我分析這個影片 https://www.youtube.com/watch?v=6_BcCthVvb8
```

Claude Code 會自動偵測並使用 speedcaster skill。

### 方法 2: 明確調用 skill

```
你: Use speedcaster skill to process https://youtu.be/abc123
```

### 方法 3: 使用 @mention（舊方式，保留相容性）

```
你: @speedcaster https://www.youtube.com/watch?v=xyz
```

## 目錄結構

```
~/.claude/skills/speedcaster/
├── skill.md              # Skill 定義與完整流程說明
├── README.md            # 本說明文件
└── scripts/
    └── youtube-transcript.sh  # YouTube 字幕提取工具
```

## 輸出格式

生成的摘要包含：

1. **TL;DR** - 120 字元精簡摘要
2. **主題分析** - 3-8 個主要主題，每個包含：
   - 重點摘要
   - 詳細內容列表
   - 時間戳記
3. **問答精華** - 3-5 個 Q&A
4. **Metadata** - 來源、時長、講者、標籤
5. **Obsidian 整合建議** - frontmatter、存放位置、連結建議

## 支援的 URL 格式

- `https://youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://youtube.com/shorts/VIDEO_ID`
- `https://youtube.com/embed/VIDEO_ID`
- `https://m.youtube.com/watch?v=VIDEO_ID`
- `https://youtube.com/live/VIDEO_ID`
- 直接 video ID（11 個字元）

## 語言處理

- **優先順序**: 英文 → 中文 → 其他語言（自動翻譯為英文）
- **輸出語言**: 繁體中文（技術術語保留英文）
- **自動翻譯**: 如果原始語言非英文/中文，會嘗試翻譯

## 錯誤處理

| 錯誤訊息 | 原因 | 解決方式 |
|---------|------|---------|
| Could not extract valid YouTube video ID | URL 格式錯誤 | 檢查 URL 或使用直接 video ID |
| No transcripts available | 影片無字幕 | 請確認影片有啟用字幕 |
| YouTube is blocking requests | 請求過於頻繁 | 稍等幾分鐘後再試 |

## 與原 Subagent 的差異

### 優點 ✅

1. **更快速**: 直接在主對話中執行，無需啟動 subprocess
2. **更清楚的 context**: 不會繼承不必要的對話歷史
3. **本地化**: script 與設定都在 `~/.claude/skills/` 下，易於管理
4. **更好的錯誤處理**: 直接在主對話中回報問題
5. **可自訂**: 可以直接編輯 `skill.md` 來調整行為

### 保留功能 ✅

- 完整的 YouTube 字幕提取能力
- 繁體中文摘要生成
- Obsidian vault 整合建議
- 多語言支援與自動翻譯

## 進階設定

### 自訂輸出格式

編輯 `skill.md` 中的 "Output Format Template" 區段來調整摘要結構。

### 調整 Script 參數

如需修改 youtube-transcript 行為，編輯：
```
~/.claude/skills/speedcaster/scripts/youtube-transcript.sh
```

## Troubleshooting

**Q: Skill 沒有被自動調用？**
A: 明確提到 "YouTube" 或 "影片" 關鍵字，或直接使用 `Use speedcaster skill`

**Q: 想要英文摘要而非中文？**
A: 在請求時明確說明：`Use speedcaster skill to process [URL], but generate summary in English`

**Q: Script 執行權限錯誤？**
A: 執行 `chmod +x ~/.claude/skills/speedcaster/scripts/youtube-transcript.sh`

## 版本歷史

- **v1.0** (2025-11-15): 從 subagent 遷移為 skill
  - 移動 youtube-transcript.sh 到 skills/speedcaster/scripts/
  - 創建完整的 skill 定義與文檔
  - 保留所有原有功能

## 相關連結

- Claude Code Skills 文檔: https://code.claude.com/docs/en/skills
- YouTube Transcript API: https://github.com/jdepoix/youtube-transcript-api
