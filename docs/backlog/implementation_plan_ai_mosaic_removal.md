# AI Mosaic Removal (Demosaic) Feature Plan

Implementing mosaic removal is a complex task that requires specialized AI models. While "perfect" restoration is impossible (data is lost), modern GAN-based models can "reconstruct" missing areas with high plausibility.

## User Review Required

> [!IMPORTANT]
> **Hardware Requirements**: AI mosaic removal is extremely resource-intensive. It requires a NVIDIA GPU (CUDA) for reasonable performance. CPU-only processing will be very slow.
>
> **Video vs. Images**:
> - **Images (Snapshots/Cover)**: Highly feasible to implement directly within JAVSTORY.
> - **Video**: Requires massive processing power and time. I suggest starting with **Image Demosaic** and providing an **Export to External Tools** (like JAVPlayer) for video.

## Proposed Changes

### [Component] AI Demosaic Engine (NEW)
#### [NEW] [demosaic_engine.py](file:///d:/App/JAVSTORY/tools/demosaic/demosaic_engine.py)
- A standalone tool that uses a pre-trained model (e.g., DeepMosaics style or a lightweight U-Net).
- Features: Mosaic detection (identifying the pixelated areas) + AI Inpainting.

### [Component] GUI Integration
#### [MODIFY] [LibraryDetail.qml](file:///d:/App/JAVSTORY/gui/qml/views/LibraryDetail.qml)
- Add an **"AI Restore"** button to the Lightbox (fullscreen image viewer).
- Provide a "Waiting" overlay while the AI processes the image.
- Show a **Before/After** comparison view.

### [Component] Backend Bridge
#### [MODIFY] [library_model.py](file:///d:/App/JAVSTORY/gui/models/library_model.py)
- Add a slot `demosaicImage(path)` that calls the backend tool and returns the processed image path.

## Open Questions

1. **Target Media**: Do you primarily want this for **Snapshots (images)** or the **Full Video**?
2. **Model Choice**: Should I include a download script for a high-quality model (~500MB), or would you prefer a "lite" version that is less accurate but faster?
3. **External Tools**: Are you interested in a feature that **automatically prepares files for JAVPlayer/DeepMosaics** so you can use professional external tools more easily?

## Verification Plan

### Manual Verification
- Open a library item with a mosaicked cover/snapshot.
- Enter Lightbox mode.
- Click "AI Restore".
- Verify that the pixelated areas are "smoothed" or "restored" with AI-generated textures.
