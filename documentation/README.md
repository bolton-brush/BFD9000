# Documentation

This folder contains logbooks (Jupyter notebooks) about various experiments and tests
related to the processes of converting the Bolton-Brush Collection to digital format.

## AutoSplit Logbook

This repository provides methods for splitting single TIFF scans containing two X-rays
into individual images, focused on the BB-Collection’s xray scans.

### Objective

The goal is to develop a reliable approach to separate double X-ray scans before
DICOMization.

### Approaches

#### 1. Classic Image Processing

Uses enhancement (noise reduction, brightness/contrast) and feature detection (edges,
lines) for unsupervised splitting.

- **Pros**: No labeled data required; runs unsupervised.
- **Cons**: Less robust; works best on consistent images.

#### 2. Machine Learning / Deep Learning

Trains a neural network to automatically split X-rays.

- **Pros**: Robust to object variation and background noise.
- **Cons**: Requires labeled training data; full deep learning approach has yet to be
  evaluated.

#### 3. Hybrid Approach

Combines classic image processing with a deep learning classification model.

- **Pros**: Simple but effective; leverages strengths of both methods.
- **Cons**: Still requires labeled data for the deep learning component; however,
  labeling for a classification model is generally easier and less time-consuming than
  labeling for an image segmentation model, as it involves assigning a single label to
  an entire image rather than annotating each pixel.

### Experiment

The complete experiment and code can be found in the Jupyter notebook:

📄 [AutoSplit Logbook](autosplit_logbook.ipynb)

### Running Locally

To run the notebook, set up a Python environment and install the required dependencies:

1. Create and activate a virtual environment:

   ```bash
   python -m venv .env
   source .env/bin/activate  # or `.env\Scripts\activate` on Windows
   ```

1. Install the dependencies:

   ```bash
   pip install torch torchvision torchaudio fastai opencv-python jupyterlab ipywidgets
   ```

You can now run the notebook and experiment with splitting X-ray scans.

______________________________________________________________________

When this feature branch is merged, the README will be updated with chapters/sections
about other notebooks found in these different feature branches.
