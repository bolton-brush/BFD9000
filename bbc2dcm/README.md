# bbc2dcm: convert scanned images from the Bolton-Brush Collection to DICOM

The scanning devices used to acquire and digitize the BBC were not DICOM compatible and
produced TIFF, PDF and STL files. the tools in this directory aid the conversion to
DICOM.

PoC package to convert BBGSC TIFFs into JPEG2000 encapsulated DICOMs.

The module is purposely divided into modules with division of concerns, so that it may
facilitate re-use and inclusion in the BFD9000 API.

## Architecture

The package consists of several modules with specific responsibilities:

- **`tiff2dcm.py`**: Main conversion module and command-line interface
- **`dicom_tags.py`**: DICOM metadata handling and image module creation
- **`jpeg2000.py`**: JPEG2000 compression utilities
- **`__init__.py`**: Package initialization and custom exception classes

## Requirements

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Required packages:

- `imagecodecs` - JPEG2000 encoding/decoding
- `numpy` - Array processing
- `pillow` - Image processing
- `pydicom` - DICOM file handling

## Installation

1. Clone or download the BFD9000 repository
1. Navigate to the bbc2dcm directory:
   ```bash
   cd BFD9000/bbc2dcm
   ```
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Command Line Interface

The main conversion tool can be used from the command line:

```bash
python -m bfd9000_dicom.tiff2dcm input.tif output.dcm [options]
```

#### Basic Usage

Convert a TIFF file to DICOM without compression:

```bash
python -m bfd9000_dicom.tiff2dcm B0013LM18y01m.tif B0013LM18y01m.dcm
```

Convert with JPEG2000 lossless compression:

```bash
python -m bfd9000_dicom.tiff2dcm B0013LM18y01m.tif B0013LM18y01m.dcm --compress
```

Use custom DICOM metadata from JSON file:

```bash
python -m bfd9000_dicom.tiff2dcm input.tif output.dcm --dicom_json metadata.json
```

#### Command Line Options

- `input_tiff`: Input TIFF file path (required)
- `output_dcm`: Output DICOM file path (required)
- `--dicom_json`: Path to JSON file containing custom DICOM tags (optional)
- `-c, --compress`: Enable JPEG2000 lossless compression (optional)

### Programmatic Usage

You can also use the package programmatically in Python:

```python
from bfd9000_dicom.tiff2dcm import convert_tiff_to_dicom

# Basic conversion
convert_tiff_to_dicom('input.tif', 'output.dcm')

# With compression
convert_tiff_to_dicom('input.tif', 'output.dcm', with_compression=True)

# With custom DICOM metadata
convert_tiff_to_dicom('input.tif', 'output.dcm', dicom_json='metadata.json')
```

## File Naming Convention

The package expects TIFF files to follow a specific naming convention for automatic
metadata extraction:

**Format**: `[PatientID][ImageType][Sex][Age].tif`

**Example**: `B0013LM18y01m.tif`

- `B0013`: Patient ID (5 characters)
- `L`: Image type (1 character)
- `M`: Patient sex (1 character - M/F)
- `18y01m`: Patient age (format: XXyYYm - years and months)

The age is automatically converted to DICOM format (total months with 'M' suffix, e.g.,
"217M").

## DICOM Metadata

### Automatically Generated Tags

The package automatically generates standard DICOM tags including:

- **Patient Information**: Patient ID, Name, Sex, Age
- **Study Information**: Study/Series/SOP Instance UIDs
- **Image Information**: Rows, Columns, Bits Allocated, Pixel Spacing
- **Device Information**: Secondary Capture device details (Vidar DosimetryPRO
  Advantage)
- **Bolton-Brush Specific**: Modality (RG), Conversion Type (DF), deidentification
  markers

### Custom Metadata via JSON

You can provide additional DICOM metadata via a JSON file. See `tests/test.dcm.json` for
an example format:

```json
{
    "00100010": {
        "vr": "PN",
        "Value": [{"Alphabetic": "Patient^Name"}]
    },
    "00080020": {
        "vr": "DA", 
        "Value": ["20241007"]
    }
}
```

## Image Processing

### Supported Formats

- **Input**: TIFF files with various bit depths and color modes
- **Color Modes**: L (grayscale), RGB, RGBA→RGB, LA→L, P→RGB
- **Bit Depths**: 8-bit and 16-bit
- **Output**: DICOM with optional JPEG2000 lossless compression

### Compression Options

- **Uncompressed**: Raw pixel data (default)
- **JPEG2000 Lossless**: Compressed pixel data with no quality loss (`--compress` flag)

## Error Handling

The package includes custom exception classes:

- `TIFF2DICOMError`: Base exception class
- `UnsupportedImageModeError`: Raised for unsupported image color modes
- `UnsupportedBitDepthError`: Raised for unsupported bit depths
- `InvalidJPEG2000CodestreamError`: Raised for invalid JPEG2000 compression

## Testing

Run the test suite:

```bash
python -m pytest tests/
```

Or run individual test files:

```bash
python -m unittest tests.test_tiff2dcm
python -m unittest tests.test_dicom_tags
```

## Examples

### Example 1: Batch Conversion

```bash
# Convert multiple files with compression
for file in *.tif; do
    python -m bfd9000_dicom.tiff2dcm "$file" "${file%.tif}.dcm" --compress
done
```

### Example 2: Custom Metadata

```python
from bfd9000_dicom.tiff2dcm import convert_tiff_to_dicom

# Convert with custom study information
convert_tiff_to_dicom(
    'B0013LM18y01m.tif',
    'B0013LM18y01m.dcm',
    dicom_json='custom_study_tags.json',
    with_compression=True
)
```

## Output

The conversion process will:

1. Extract patient metadata from the filename
1. Load and process the TIFF image
1. Generate required DICOM metadata
1. Apply optional JPEG2000 compression
1. Save the resulting DICOM file

Success message: `"Saved DICOM file at [output_path]"`
