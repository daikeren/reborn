#!/bin/bash

# Set proper encoding for handling Chinese characters
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title YouTube Transcript to SRT
# @raycast.mode fullOutput
# @raycast.packageName YouTube Tools

# Optional parameters:
# @raycast.icon 📺
# @raycast.argument1 { "type": "text", "placeholder": "YouTube URL", "optional": false }

# Documentation:
# @raycast.description Extract YouTube transcript from URL and output as SRT
# @raycast.author Andy Dai
# @raycast.authorURL https://github.com/daikeren

# Function to URL decode a string
url_decode() {
  local url="$1"
  # Replace %XX with actual characters
  printf '%b' "${url//%/\\x}"
}

# Function to sanitize URL input
sanitize_url() {
  local url="$1"
  
  # Remove leading/trailing whitespace
  url="${url#"${url%%[![:space:]]*}"}"
  url="${url%"${url##*[![:space:]]}"}"
  
  # Remove potential quotes
  url="${url#\"}"
  url="${url%\"}"
  url="${url#\'}"
  url="${url%\'}"
  
  # URL decode if needed
  if [[ "$url" =~ %[0-9A-Fa-f]{2} ]]; then
    url=$(url_decode "$url")
  fi
  
  echo "$url"
}

# Function to extract YouTube ID from various URL formats
extract_youtube_id() {
  local url="$1"
  local youtube_id=""
  
  # Sanitize input
  url=$(sanitize_url "$url")
  
  echo "DEBUG: Processing URL: '$url'" >&2

  # Check if input is already just an ID (11 characters)
  if [[ "$url" =~ ^[a-zA-Z0-9_-]{11}$ ]]; then
    youtube_id="$url"
    echo "DEBUG: Matched as direct video ID" >&2
  # Most flexible pattern: extract v= parameter from any YouTube URL
  elif [[ "$url" =~ [\?\&]v=([a-zA-Z0-9_-]{11}) ]]; then
    youtube_id="${BASH_REMATCH[1]}"
    echo "DEBUG: Matched v= parameter in URL" >&2
  # Shortened youtu.be URL
  elif [[ "$url" =~ youtu\.be/([a-zA-Z0-9_-]{11}) ]]; then
    youtube_id="${BASH_REMATCH[1]}"
    echo "DEBUG: Matched as youtu.be URL" >&2
  # YouTube shorts URL
  elif [[ "$url" =~ youtube\.com/shorts/([a-zA-Z0-9_-]{11}) ]]; then
    youtube_id="${BASH_REMATCH[1]}"
    echo "DEBUG: Matched as YouTube shorts URL" >&2
  # Embedded URL
  elif [[ "$url" =~ youtube\.com/embed/([a-zA-Z0-9_-]{11}) ]]; then
    youtube_id="${BASH_REMATCH[1]}"
    echo "DEBUG: Matched as embedded URL" >&2
  # YouTube live URL
  elif [[ "$url" =~ youtube\.com/live/([a-zA-Z0-9_-]{11}) ]]; then
    youtube_id="${BASH_REMATCH[1]}"
    echo "DEBUG: Matched as live URL" >&2
  # Mobile URL
  elif [[ "$url" =~ m\.youtube\.com/watch.*v=([a-zA-Z0-9_-]{11}) ]]; then
    youtube_id="${BASH_REMATCH[1]}"
    echo "DEBUG: Matched as mobile URL" >&2
  else
    echo "DEBUG: No regex patterns matched for URL: '$url'" >&2
  fi

  echo "DEBUG: Extracted video ID: '$youtube_id'" >&2
  echo "$youtube_id"
}

# Get the YouTube URL from the argument
youtube_url="$1"

# Validate input
if [ -z "$youtube_url" ]; then
  echo "Error: No URL provided"
  echo "Usage: $0 <YouTube URL>"
  exit 1
fi

# Extract the video ID
video_id=$(extract_youtube_id "$youtube_url" 2>/dev/null)

# Enhanced validation
if [ -z "$video_id" ] || [ ${#video_id} -ne 11 ]; then
  echo "Error: Could not extract valid YouTube video ID from URL"
  echo "Provided URL: '$youtube_url'"
  echo ""
  echo "Supported URL formats:"
  echo "  - https://youtube.com/watch?v=VIDEO_ID"
  echo "  - https://youtu.be/VIDEO_ID"
  echo "  - https://youtube.com/shorts/VIDEO_ID"
  echo "  - https://youtube.com/embed/VIDEO_ID"
  echo "  - https://m.youtube.com/watch?v=VIDEO_ID"
  echo "  - https://youtube.com/live/VIDEO_ID"
  echo "  - Direct video ID (11 characters)"
  echo ""
  echo "Re-running with debug output:"
  extract_youtube_id "$youtube_url"
  exit 1
fi

# Try to get transcript with language fallback
echo "Extracting transcript for video ID: $video_id" >&2

# Validate video ID one more time before API call
if ! [[ "$video_id" =~ ^[a-zA-Z0-9_-]{11}$ ]]; then
  echo "Error: Invalid video ID format: '$video_id'"
  exit 1
fi

# Escape video ID if it starts with hyphen to prevent it being treated as an option
escaped_video_id="$video_id"
if [[ "$video_id" =~ ^- ]]; then
  escaped_video_id="\\$video_id"
  echo "Video ID starts with hyphen, escaping: '$escaped_video_id'" >&2
fi

# First attempt with English
transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt --languages en 2>&1)

# Check if we got an error (youtube_transcript_api returns 0 even on failure)
if echo "$transcript_output" | grep -q "Could not retrieve a transcript"; then
  echo "English transcript not available, checking other options..." >&2
  
  # Check if the error message contains available languages
  if echo "$transcript_output" | grep -q "transcripts are available in the following languages"; then
    # Try to extract available language codes
    # First look for manually created transcripts
    if echo "$transcript_output" | grep -q "MANUALLY CREATED"; then
      # Extract language code from lines like " - zh-TW ("Chinese (Taiwan)")[TRANSLATABLE]"
      first_lang=$(echo "$transcript_output" | sed -n '/MANUALLY CREATED/,/GENERATED\|TRANSLATION/p' | grep -oE ' - [a-zA-Z]{2}(-[A-Z]{2})?' | head -1 | sed 's/ - //')
      
      if [ -n "$first_lang" ]; then
        echo "Found manually created transcript in language: $first_lang" >&2

        # Check if it's a Chinese variant (zh, zh-TW, zh-CN, zh-HK, etc.)
        if [[ "$first_lang" =~ ^zh ]]; then
          echo "Using Chinese transcript directly..." >&2
          transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt --languages "$first_lang" 2>&1)
        else
          # For non-English, non-Chinese languages, try to translate to English
          echo "Non-English/Chinese transcript found, checking if English translation is available..." >&2
          if echo "$transcript_output" | sed -n '/TRANSLATION LANGUAGES/,$p' | grep -q ' - en '; then
            echo "Translating $first_lang transcript to English..." >&2
            transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt --languages "$first_lang" --translate en 2>&1)
          else
            # If no English translation available, use original language
            echo "No English translation available, using original $first_lang transcript..." >&2
            transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt --languages "$first_lang" 2>&1)
          fi
        fi
      fi
    fi
    
    # If no manually created transcripts, check generated ones
    if echo "$transcript_output" | grep -q "Could not retrieve a transcript" && echo "$transcript_output" | grep -q "GENERATED"; then
      # Look for generated transcripts
      gen_lang=$(echo "$transcript_output" | sed -n '/GENERATED/,/TRANSLATION/p' | grep -oE ' - [a-zA-Z]{2}(-[A-Z]{2})?' | head -1 | sed 's/ - //')
      
      if [ -n "$gen_lang" ]; then
        echo "Found generated transcript in language: $gen_lang" >&2

        # Check if it's Chinese or should be translated
        if [[ "$gen_lang" =~ ^zh ]]; then
          echo "Using Chinese generated transcript..." >&2
          transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt --languages "$gen_lang" 2>&1)
        elif echo "$transcript_output" | sed -n '/TRANSLATION LANGUAGES/,$p' | grep -q ' - en '; then
          echo "Translating $gen_lang transcript to English..." >&2
          transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt --languages "$gen_lang" --translate en 2>&1)
        else
          transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt --languages "$gen_lang" 2>&1)
        fi
      fi
    fi
    
    # Last resort: try without language specification
    if echo "$transcript_output" | grep -q "Could not retrieve a transcript"; then
      echo "Trying to get any available transcript..." >&2
      transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt 2>&1)
    fi
  else
    # If we can't parse the error, try without language specification
    echo "Trying to get any available transcript..." >&2
    transcript_output=$(uvx youtube_transcript_api "$escaped_video_id" --format srt 2>&1)
  fi
fi

# Check final result
if echo "$transcript_output" | grep -q "Could not retrieve a transcript"; then
  echo "❌ Failed to extract transcript"
  
  # Provide specific error messages
  if echo "$transcript_output" | grep -q "YouTube is blocking requests"; then
    echo "Error: YouTube is blocking requests from your IP address."
    echo "This may be due to too many requests or using a cloud provider IP."
  elif echo "$transcript_output" | grep -q "No transcripts were found"; then
    echo "Error: No transcripts available in the requested languages."
    
    # Show available languages if present in error
    if echo "$transcript_output" | grep -q "transcripts are available in the following languages"; then
      echo ""
      echo "Available transcripts:"
      echo "$transcript_output" | sed -n '/MANUALLY CREATED/,/TRANSLATION LANGUAGES/p' | grep -E '^ - '
    fi
  else
    echo "Error details: $transcript_output"
  fi
  
  exit 1
else
  # Output SRT to stdout
  printf '%s\n' "$transcript_output"
fi
