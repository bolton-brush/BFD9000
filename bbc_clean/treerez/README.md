# TreeRez: Simple commandline utility to copy & resize TIFF scans

This tool was developed to produce training data for a machine/deep learning algorithm.
It was designed to automatically extract a small subset (5-10%) of the BB-Collection,
reformat it to PNG, shrink and remove white noise.

This tool is part of the larger project of cleaning up the Bolton-Brush Legacy
Collection at Case Western Reserve University and converting them into DICOM.

## Introduction

The BB-Legacy Collection was scanned and archived by humans, without many automation
tools over many years, by many different researchers. Consequently, the images, the file
names and the folders they are located in, are not consistently named or oriented.
Manual clean up would take many hundreds of human work hours.

Automation is therefore required, and machine/deep learning could be a great tool for
this task. However, it needs to be trained first. Training requires a set of clean data,
which means that the orientation of these images will need to be known. Hence, we need
to rotate, flip and segment.

For automatic correction of rotation, flipping, segmentation, etc., a subset of the
scans must be prepared as a training set. For performance reasons, the resolution of the
training set should be lower than that of the original. Furthermore, the scans should be
examined and any large borders removed to enhance the effectiveness and improve the
scoring potential of the trained models.

TreeRez lets you randomly sample a subset of patient folders, copying and resizing TIFF
scans, automatically trimming white borders and converting them to RGB PNGs.

## Installation

create a python env as usual (venv, pipenv, conda, etc..)

`pip install -r requirements.txt`

## Usage

```
python treerez.py -h

usage: treerez.py [-h] [-n] [-r] [-q] [-t] source destination

positional arguments:
  source              source folder - contains patients folders with xray-scans
  destination         destination folder - sampled xray-scans will be copied and resized here

options:
  -h, --help          show this help message and exit
  -n, --dryrun        Do nothing, dry run
  -r , --resolution   target resolution for copied xray-scans (default: 1024)
  -q , --quantity     number of sampled patients (default: 1)
  -t , --trim         auto-trimming threshold - from 0 (black) to 255 (white) (default: 240)
```

You can find more details in the
[treerez logbook](/documentation/treerez_logbook.ipynb).
