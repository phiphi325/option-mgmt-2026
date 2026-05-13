# Skill: advanced-image-techniques

| | |
|---|---|
| **ID** | `seed_skill_advanced_image_techniques` |
| **Description** | Advanced image generation techniques and prompting patterns |
| **Tags** | — |
| **When to use** | — |

---

# Advanced Image Generation Techniques

This skill documents professional patterns for using the GenerateImage tool with Google's Gemini image models (Nano Banana).

## Model Selection Guide

### Flash Model (gemini-2.5-flash-image)
- **Speed**: Fast generation (~5-10 seconds)
- **Multi-image**: Can generate 1-4 images at once
- **Best for**: Quick iterations, variations, prototyping
- **Input limit**: Up to 3 reference images

### Pro Model (gemini-3-pro-image-preview)
- **Quality**: Higher fidelity, better details
- **Resolution**: Supports up to 4K output
- **Text rendering**: Superior text-in-image quality
- **Best for**: Final production assets, text-heavy images
- **Input limit**: Up to 5 reference images (but only 1 output)

## Aspect Ratio Reference

| Ratio | Resolution (Flash) | Use Case |
|-------|-------------------|----------|
| 1:1 | 1024x1024 | Social media, avatars, icons |
| 16:9 | 1344x768 | Presentations, video thumbnails |
| 9:16 | 768x1344 | Stories, mobile wallpapers |
| 4:3 | 1184x864 | Traditional photos, displays |
| 3:4 | 864x1184 | Portrait photos |
| 4:5 | 896x1152 | Instagram posts |
| 5:4 | 1152x896 | Landscape Instagram |
| 2:3 | 832x1248 | Portrait photography, posters |
| 3:2 | 1248x832 | Landscape photography |
| 21:9 | 1536x672 | Cinematic, banners, ultrawide |

## Advanced Techniques

### 1. Style Transfer

Apply the visual style of one image to new content.

**Pattern:**
```
inputImages: [style_reference_url]
prompt: "Create a [subject] in the exact style of this reference image"
```

**Example:**
```json
{
  "prompt": "A serene mountain landscape in the exact artistic style of this reference image",
  "inputImages": ["https://example.com/van-gogh-style.jpg"],
  "aspectRatio": "16:9"
}
```

### 2. Product Placement

Place products naturally into scenes.

**Pattern:**
```
inputImages: [product_image_url]
prompt: "Place this product naturally in [scene description]"
```

**Example:**
```json
{
  "prompt": "Place this coffee mug on a cozy desk setup with morning sunlight streaming through a window",
  "inputImages": ["https://example.com/product-mug.png"],
  "aspectRatio": "4:3"
}
```

### 3. Background Replacement

Change the background while preserving the subject.

**Pattern:**
```
inputImages: [subject_image_url]
prompt: "Keep the [subject] exactly the same, change the background to [new environment]"
```

**Example:**
```json
{
  "prompt": "Keep the person exactly the same, change the background to a tropical beach at sunset",
  "inputImages": ["https://example.com/portrait.jpg"],
  "personGeneration": "allow_adult"
}
```

### 4. Image Combination/Collage

Merge multiple images into a cohesive composition.

**Pattern:**
```
inputImages: [image1_url, image2_url, image3_url]
prompt: "Combine these elements into [description of desired composition]"
```

**Example:**
```json
{
  "prompt": "Create a fantasy scene combining the castle from the first image, the dragon from the second, and the magical forest from the third",
  "inputImages": ["castle.jpg", "dragon.jpg", "forest.jpg"],
  "aspectRatio": "16:9"
}
```

### 5. Object Addition/Removal

Modify specific elements in an image.

**Pattern (Addition):**
```
inputImages: [original_image_url]
prompt: "Add [object] to [location in image]"
```

**Pattern (Removal):**
```
inputImages: [original_image_url]
prompt: "Remove [object] from the image, fill naturally"
```

### 6. Text-Heavy Images (Use Pro Model)

Generate images with readable text.

**Example:**
```json
{
  "prompt": "A professional book cover with the title 'The Art of AI' in elegant serif font, subtitle 'A Journey Through Machine Learning', author name 'Dr. Sarah Chen' at bottom",
  "model": "gemini-3-pro-image-preview",
  "aspectRatio": "2:3",
  "resolution": "2K"
}
```

### 7. Multiple Variations

To generate multiple options, call GenerateImage multiple times with parallel tool calls.
Vary the prompt for distinct options rather than generating duplicates.

### 8. Iterative Refinement

Build on previous generations.

**Workflow:**
1. Generate initial image
2. Use result as inputImage for next iteration
3. Refine with specific adjustments

**Example Sequence:**
```
Turn 1: "A cozy reading nook with warm lighting" → [generates base image]
Turn 2: inputImages: [result_url], "Add a sleeping cat on the armchair"
Turn 3: inputImages: [result_url], "Make the lighting warmer, add more books on the shelf"
```

### 9. Outpainting (Image Expansion)

Expand an image beyond its original boundaries.

**Pattern:**
```
inputImages: [original_image_url]
prompt: "Expand this image to show more of the [surrounding environment], maintain the same style and lighting"
aspectRatio: [wider ratio than original]
```

## Best Practices

1. **Be specific**: Detailed prompts yield better results
2. **Use Pro for text**: When text readability matters, always use Pro model
3. **Iterate**: Don't expect perfection on first try - use results as inputs for refinement
4. **Match aspect ratios**: Choose ratios that fit your final use case
5. **Control people**: Use `personGeneration: "dont_allow"` for brand safety
6. **Generate variations**: Make multiple parallel GenerateImage calls with distinct prompts

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Text is blurry/unreadable | Use Pro model with 2K+ resolution |
| Style doesn't match reference | Add "in the exact style of this reference image" |
| Product looks unnatural | Describe lighting and perspective to match scene |
| Unwanted people in output | Set `personGeneration: "dont_allow"` |
| Need more options | Make multiple parallel calls with varied prompts |
