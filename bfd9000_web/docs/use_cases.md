# Use Cases

See also: [Permissions Reference](permissions.md)

The BFD9000 shall be able to accommodate the following use cases.

______________________________________________________________________

## UC01: Add New Records

### Actors

- **Operator**: A human individual who needs to digitize a physical record into a
  digital record
- **System**: BFD9000 web application
- **BFD9010**: The bridge used to connect the scanner with the system
- **Scanner**: The acquisition modality used to convert the physical record into the
  digital record

### Prerequisites

- Operator has turned on the scanner
- Operator has logged into a workstation connected to the scanner
- Operator has authenticated into the system using CAS SSO (case.edu credentials)
- Operator has launched the BFD9010 bridge on the workstation with the scanner connected
- Operator has located and identified the physical record to be digitized and archived

### Steps

1. Operator searches for the subject related to the physical record. If the subject
   doesn't exist, the operator creates a new subject with a minimum of: subject
   identifier, collection name, and sex
1. Operator searches for existing records by age at encounter and record type (e.g.,
   Lateral, PA, Hand) to ensure the record hasn't already been digitized
1. If the record doesn't exist, the operator proceeds to add a new record
1. System displays a new view showing the detected scanner and instructions for use
   (i.e., how to place the physical record into the scanner)
1. Operator clicks the scan button and waits for the scan to complete
1. Operator is presented with a preview of the scanned record and verifies that all
   metadata is appropriately selected (record type, orientation, operator name, date of
   acquisition, encounter date, collection)
1. Operator makes any necessary corrections to the metadata using the appropriate fields
   and dropdown menus (selections preferred over manual text entry)
1. Once the operator confirms, the digitized record is added to the database. System
   proceeds to convert it to DICOM and uploads it to a PACS or other DICOM node

______________________________________________________________________

## UC02: Browse for Records

Operators need to be able to search for and view specific records.

### Actors

- **Operator**: A human individual who needs to search for and view records
- **System**: BFD9000 web application

### Prerequisites

- Operator has logged into a workstation
- Operator has authenticated into the system using CAS SSO (case.edu credentials)

### Steps

1. Operator searches for or browses subjects. System displays a list of subjects with:
   number of encounters per subject, total number of records, sex, dental classification
   (and/or other clinical information), and collection
1. Operator clicks on a subject. System displays the subject detail view with more
   clinical details and a list of all encounters for the subject. The encounter list
   shows: age of subject at encounter, number of records acquired during encounter, and
   types of records by modality (e.g., RG, M3D, PX, DX)
1. Operator selects an encounter. System displays each record for the encounter, showing
   thumbnails and record details such as: file size, image type, orientation, and other
   relevant metadata
1. Operator views the full record

______________________________________________________________________

## UC03: Record Maintenance and Administration

### Actors

- **Administrator**: A human individual with administration privileges
- **System**: BFD9000 web application (Django admin interface)

### Prerequisites

- Administrator has logged into a workstation
- Administrator has authenticated into the system using CAS SSO (case.edu credentials)
- Administrator has appropriate permissions to access the admin interface

### Steps

1. Administrator opens the Django admin interface
1. Administrator navigates to the appropriate model (Subject, Encounter, or Record)
1. Administrator selects the entity to modify or delete
1. Administrator performs the desired action (edit metadata, delete record, etc.)
1. System saves the changes and logs the administrative action

______________________________________________________________________

## UC04: Export and Sharing

**Status**: Not yet implemented

Operators should be able to export and share records with other users in DICOM format.

### Actors

- **Operator**: A human individual who needs to export or share records
- **System**: BFD9000 web application

### Prerequisites

- Operator has logged into a workstation
- Operator has authenticated into the system using CAS SSO (case.edu credentials)
- Operator has appropriate permissions to export or share records

### Steps

TODO
