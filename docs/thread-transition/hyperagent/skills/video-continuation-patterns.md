# Skill: video-continuation-patterns

| | |
|---|---|
| **ID** | `seed_skill_video_continuation` |
| **Description** | Patterns for video continuation and scene chaining |
| **Tags** | — |
| **When to use** | — |

---

# Video Continuation Patterns

This skill documents techniques for seamlessly extending AI-generated videos.

## Two Approaches

| Approach | Time Window | Quality | How It Works |
|----------|-------------|---------|---------------|
| **Native Extension** | < 48 hours | Best | Uses Google's video object reference |
| **Frame Extraction** | Infinite | Good | Extracts last frame, uses as firstFrameImage |

## Approach 1: Native Extension (Recommended When Available)

When a Veo video was generated within the last ~48 hours, use native extension for best results.

**Usage:**
```json
{
  "tool": "GenerateVideo",
  "input": {
    "extendFromVideo": "/threads/abc/media/video.mp4",
    "prompt": "The character turns and walks toward the sunset"
  }
}
```

**Constraints:**
- Only works with Veo-generated videos
- Must be within ~48 hours of original generation
- Output is always 720p
- Adds 7 seconds per extension
- Maximum 20 extensions (148 seconds total)

**Benefits:**
- Motion continuity (analyzes velocity, direction)
- Audio continuity (sound design matches)
- No visual seams

## Approach 2: Frame Extraction (Infinite Continuation)

For videos older than 48 hours, or when native extension fails, extract the last frame and use it as the starting point.

**Step 1: Download the video**
```bash
curl -o video.mp4 "viewUrl"
```

**Step 2: Extract last frame with ffmpeg**
```bash
ffmpeg -sseof -0.1 -i video.mp4 -update 1 -q:v 2 last_frame.jpg
```

**Step 3: Save and get a viewUrl**
```json
{
  "tool": "SaveFile",
  "input": { "path": "last_frame.jpg" }
}
```

**Step 4: Generate continuation using extracted frame**
```json
{
  "tool": "GenerateVideo",
  "input": {
    "firstFrameImage": "[viewUrl from step 3]",
    "prompt": "Continue the scene: the character turns and walks toward the sunset"
  }
}
```

**Benefits:**
- Works with any age video
- Can chain indefinitely
- Can modify direction/style between segments

**Limitations:**
- Visual continuity only (no motion analysis)
- Audio starts fresh each segment
- Requires more explicit prompting for seamless transitions

## Choosing the Right Approach

```
Is video < 48 hours old AND was generated with current code?
├── YES → Try native extension (GenerateVideo with extendFromVideo)
│         If it fails with "missing extension data", use frame extraction
└── NO  → Use frame extraction (E2BFetchUrl + ffmpeg + firstFrameImage)
```

## Tips for Seamless Continuations

1. **Match the ending motion**: If the video ends with a character walking right, continue that motion
2. **Reference previous audio**: "Continuing the ambient forest sounds..."
3. **Use consistent style language**: Copy style descriptors from original prompt
4. **Consider transitions**: Sometimes ending one scene and starting fresh is better than forcing continuity

## Example: Creating a 30-Second Story

**Initial video (8s):**
```json
{ "prompt": "A cat sits on a windowsill watching birds, curious expression, warm afternoon light" }
```

**Extension 1 (+7s = 15s):**
```json
{ "extendFromVideo": "[viewUrl]", "prompt": "The cat's eyes widen as a bird lands on the windowsill" }
```

**Extension 2 (+7s = 22s):**
```json
{ "extendFromVideo": "[viewUrl]", "prompt": "The cat pounces playfully at the window, bird flies away" }
```

**Extension 3 (+7s = 29s):**
```json
{ "extendFromVideo": "[viewUrl]", "prompt": "The cat looks disappointed, then curls up to nap in the sunlight" }
```

## FFmpeg Commands Reference

| Task | Command |
|------|----------|
| Extract last frame | `ffmpeg -sseof -0.1 -i video.mp4 -update 1 -q:v 2 /home/user/outputs/last_frame.jpg` |
| Extract frame at 5 seconds | `ffmpeg -ss 5 -i video.mp4 -frames:v 1 /home/user/outputs/frame_5s.jpg` |
| Extract multiple frames | `ffmpeg -i video.mp4 -vf "fps=1" /home/user/outputs/frame_%04d.jpg` |
| Get video duration | `ffprobe -v error -show_entries format=duration -of csv=p=0 video.mp4` |
