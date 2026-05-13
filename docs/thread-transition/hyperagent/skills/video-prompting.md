# Skill: video-prompting

| | |
|---|---|
| **ID** | `seed_skill_video_prompting` |
| **Description** | Best practices for video generation prompting |
| **Tags** | — |
| **When to use** | — |

---

# Video Prompting Techniques for Veo 3.1

This skill documents professional techniques for creating effective video generation prompts using Google's Veo 3.1 model.

## Prompt Structure Formula

**[Subject] + [Action/Movement] + [Scene/Setting] + [Style/Mood] + [Camera/Cinematography]**

**Example:** "A golden retriever running through autumn leaves in a sunlit forest, cinematic warm tones, tracking shot following the dog, shallow depth of field"

## Camera Movement Glossary

| Movement | Description | When to Use |
|----------|-------------|-------------|
| Dolly in/out | Camera moves toward/away on tracks | Reveal or emphasize subject |
| Crane shot | Camera moves vertically up/down | Establish scale, dramatic reveals |
| Tracking shot | Camera follows subject laterally | Action sequences, following motion |
| Pan | Camera rotates horizontally (fixed position) | Scan environments, follow action |
| Tilt | Camera rotates vertically (fixed position) | Reveal height, dramatic looks |
| Orbit | Camera circles around subject | 360-degree character intros |
| Steadicam | Smooth handheld movement | Immersive following shots |
| Handheld | Intentional camera shake | Documentary feel, tension, realism |
| Zoom | Lens focal length changes | Quick emphasis, crash zoom |
| Static | No camera movement | Dialogue scenes, contemplative shots |

## Shot Composition

| Shot Type | Frame | Best For |
|-----------|-------|----------|
| Extreme close-up (ECU) | Eyes, small details | Emotional intensity, texture |
| Close-up (CU) | Face/head fills frame | Emotion, dialogue reactions |
| Medium close-up (MCU) | Chest and up | Conversation, expressions |
| Medium shot (MS) | Waist up | Gestures, body language |
| Medium wide (MW) | Knees up | Action with context |
| Wide shot (WS) | Full body + environment | Context, movement |
| Establishing shot | Location overview | Set the scene, transitions |
| Over-the-shoulder (OTS) | Behind one person | Dialogue scenes |
| POV | From character's eyes | Immersion, tension |
| Bird's eye | Directly overhead | God's view, patterns |
| Low angle | Camera looks up | Power, dominance |
| High angle | Camera looks down | Vulnerability, overview |
| Dutch angle | Tilted frame | Unease, stylization |

## Lighting Descriptions

| Lighting | Description | Mood |
|----------|-------------|------|
| Golden hour | Warm, soft sunlight (sunrise/sunset) | Romantic, nostalgic, warm |
| Blue hour | Cool twilight ambiance | Mysterious, calm, melancholic |
| High-key | Bright, minimal shadows | Upbeat, clean, cheerful |
| Low-key | Deep shadows, dramatic contrast | Noir, mysterious, dramatic |
| Silhouette | Backlit, subject in shadow | Dramatic, anonymous, artistic |
| Neon | Colorful artificial lighting | Cyberpunk, nightlife, modern |
| Natural | Realistic daylight or practical lights | Documentary, authentic |
| Volumetric | Visible light rays through atmosphere | Ethereal, dramatic, spiritual |
| Rim light | Light outlining subject edge | Separation, drama |
| Soft diffused | Even, shadowless lighting | Beauty, commercial |

## Audio Prompting (Native in Veo 3.1)

Veo 3.1 generates synchronized audio natively. Include audio cues in your prompts:

### Dialogue
Use quotes with emotion/delivery cues:
- "Hello, world!" she says excitedly
- A man murmurs, "This must be it. That's the secret code."
- "What did you find?" the woman whispers nervously

### Ambient Sounds
Describe the soundscape:
- rain pattering on windows
- city traffic humming in the background
- wind rustling through autumn leaves
- waves crashing on rocks
- birds chirping at dawn
- footsteps echoing in an empty corridor

### Music/Mood Cues
- tense silence broken by a heartbeat
- upbeat electronic music
- dramatic orchestral swell
- soft piano melody
- pulsing bass rhythm
- nostalgic acoustic guitar

## Generation Modes

| Mode | Parameters | Best For |
|------|------------|----------|
| Text-to-Video | prompt only | General creative generation |
| Image-to-Video | firstFrameImage | Animate a photo, consistent starting point |
| Frame-Controlled | firstFrameImage + lastFrameImage | Transitions, morphs (requires 8s) |
| Style-Guided | referenceImages (up to 3) | Consistent visual style across videos |

## Style References

| Style | Key Prompting Words |
|-------|-------------------|
| Cinematic | "cinematic", "film grain", "anamorphic", "shallow DOF" |
| Documentary | "handheld", "natural lighting", "observational" |
| Commercial | "clean", "bright", "product shot", "studio lighting" |
| Film noir | "black and white", "high contrast", "dramatic shadows" |
| Sci-fi | "futuristic", "neon", "holographic", "chrome" |
| Fantasy | "ethereal", "magical", "mystical lighting" |
| Horror | "dark", "unsettling", "atmospheric", "slow reveal" |
| Animation | "3D animated", "stylized", "Pixar-style" |

## Example Prompts

### Cinematic Dialogue Scene
```
A close up of two people staring at a cryptic drawing on a wall, torchlight flickering.
A man murmurs, "This must be it. That's the secret code." The woman looks at him 
whispering excitedly, "What did you find?"
```

### Action Sequence
```
Tracking shot following a motorcycle racing through neon-lit city streets at night,
rain-slicked roads reflecting colorful signs, engine roaring, tires screeching on 
tight turns, cinematic anamorphic lens flares
```

### Nature Documentary
```
Slow motion extreme close-up of a hummingbird hovering at a red flower, iridescent 
green feathers catching golden hour sunlight, wings beating rapidly creating a soft 
blur, soft ambient forest sounds with bird calls in the distance
```

### Product Commercial
```
Smooth dolly shot revealing a sleek smartphone on a minimalist white surface, soft 
studio lighting with subtle reflections, shallow depth of field, premium aesthetic,
gentle ambient music
```

### Emotional Character Moment
```
Medium close-up of a woman sitting by a rain-streaked window, soft natural light 
illuminating her face, she sighs softly "I miss you," quiet piano melody plays, 
contemplative and melancholic mood
```

## Best Practices

1. **Structure your prompts**: Follow the formula for consistent results
2. **Be specific about camera**: Include movement AND composition
3. **Describe audio**: Veo 3.1's native audio is powerful - use it
4. **Include lighting**: Lighting sets the mood more than anything
5. **Use style references**: Reference film styles for consistent aesthetics
6. **Consider duration**: Match content complexity to video length
7. **Use referenceImages**: For style consistency across multiple videos
8. **Test with fast mode**: Iterate quickly before using standard quality
