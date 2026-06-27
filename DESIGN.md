# Netflix Design System

## Brand Identity
Netflix is an immersive, cinematic, and bold entertainment platform. The design is engineered to get out of the way of the content. The UI is predominantly black and dark grey, allowing the vibrant colors of movie posters and trailers to pop. The signature Netflix Red is used sparingly but effectively for primary actions and brand recognition.

## Colors

### Backgrounds
- `background-base`: `#000000` (Deep black for the main canvas)
- `background-surface`: `#141414` (Dark grey for secondary backgrounds like rows and modals)
- `background-hover`: `#2f2f2f` (Lighter grey for hover states on cards)

### Text
- `text-primary`: `#ffffff` (Pure white for high contrast readability)
- `text-secondary`: `#b3b3b3` (Muted grey for descriptions, metadata, and secondary links)
- `text-muted`: `#808080` (Darker grey for disabled states or minor details)

### Brand & Accents
- `brand-red`: `#E50914` (The iconic Netflix Red used for logos, primary buttons, and active states)
- `brand-red-hover`: `#C11119` (Darker red for button hovers)
- `brand-red-active`: `#B00710` (Even darker red for active/pressed states)

## Typography
- **Primary Font**: Netflix Sans (Fallback: Helvetica Neue, Helvetica, Arial, sans-serif)
- **Scale**:
  - `h1` (Hero Title): 48px to 64px, Bold, tight tracking.
  - `h2` (Row Title): 24px to 32px, Bold.
  - `body-large`: 18px, Regular.
  - `body`: 16px, Regular.
  - `small`: 14px, Regular or Medium.

## Spacing & Grid
- **Base Unit**: 8px.
- **Row Gap**: 40px to 60px between horizontal scrolling rows.
- **Card Spacing**: 4px to 8px between individual movie cards in a row.

## Components

### Buttons
- **Primary Play Button**: White background (`#ffffff`), black text (`#000000`), bold font, icon on the left. Hover state adds a slight opacity/dimming.
- **Secondary Button (More Info)**: Translucent grey background (`rgba(109, 109, 110, 0.7)`), white text (`#ffffff`), icon on the left.
- **Border Radius**: 4px (slightly rounded corners, not fully pill-shaped).

### Cards (Movie Posters)
- **Aspect Ratio**: 16:9 (for trailers/previews) or 2:3 (for standard vertical posters).
- **Hover Effect**: Cards scale up by ~1.1x to 1.5x on hover, expanding over adjacent cards, revealing a preview video and metadata below the image.
- **Shadows**: Heavy drop shadows on hovered cards to separate them from the background (`0 10px 20px rgba(0,0,0,0.75)`).

### Navigation (App Bar)
- **Gradient**: Top navigation bar transitions from solid black to transparent using a vertical gradient (`linear-gradient(to bottom, rgba(0,0,0,0.7) 10%, rgba(0,0,0,0))`).
- **Scroll Behavior**: Turns solid `#141414` after scrolling down.

### Modals / Popovers
- **Background**: `#181818` with a strong drop shadow.
- **Close Button**: Circular icon button, absolute positioned at top right.

## Effects
- **Vignette/Gradients**: Heavy use of black gradients overlaying the bottom and sides of hero images to ensure white text is always readable regardless of the image behind it.
- **Transitions**: Smooth, fast transitions (`~200-300ms ease-in-out`) for card expansions to make browsing feel responsive and fluid.