---
name: vision
description: Use when you want to analyze, describe, or extract information from an image. Handles scientific figures, plots, experimental setups, and general image Q&A.
---

# Vision Skill

Analyze an image with an image expert. 

## Usage

Run the script with an image path and a prompt:

```bash
python scripts/vision.py <image_path> "<prompt>"
```

### Examples

```bash
# Describe a plot
python scripts/vision.py spectrum.png "Identify the emission lines in this spectrum"

# Read values from a figure
python scripts/vision.py graph.png "What is the peak wavelength shown in this plot?"