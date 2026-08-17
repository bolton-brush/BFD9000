# BFD9000 Permissions Reference

## Roles and Responsibilities

| Role      | Description                                                     |
| --------- | --------------------------------------------------------------- |
| User      | Authenticated; can view and create records (scan workflow only) |
| Curator   | Can add/change Subjects and Encounters (no delete)              |
| Superuser | All rights, including deletes and admin user/group management   |

## API Permissions Matrix (Subject, Encounter, Record)

| Action            | User | Curator | Superuser |
| ----------------- | ---- | ------- | --------- |
| List/Detail (GET) | ✓    | ✓       | ✓         |
| Create Subject    |      | ✓       | ✓         |
| Update Subject    |      | ✓       | ✓         |
| Delete Subject    |      |         | ✓         |
| Create Encounter  |      | ✓       | ✓         |
| Update Encounter  |      | ✓       | ✓         |
| Delete Encounter  |      |         | ✓         |
| Create Record     | ✓    | ✓       | ✓         |
| Update Record     | ✓    | ✓       | ✓         |
| Delete Record     |      |         | ✓         |
| Auth: User Mgmt   |      |         | ✓         |

- Curator has *no* rights for user/group/permission admin.
- DELETE is strictly superuser-only.

## Current Implementation Notes

- Group: `Curator` is auto-created by management command (`setup_curator_group`).
- Permissions: Curator keeps `add/change` on Subject/Encounter.
- Guardrails: command removes Curator delete perms for Subject/Encounter/Record and
  removes all `auth` app perms.
- "New Subject" and "New Encounter" UI is only displayed where user has appropriate
  permissions.

## How to Change Curator Permissions Later

To grant additional rights (e.g., delete) to the Curator group, run:

```
$ python manage.py setup_curator_group  # Safe to re-run anytime
```

Or, manually through Django admin:

1. Open the Django admin at `/admin/` as a superuser.
1. Navigate to Groups > Curator.
1. Add or remove permissions (e.g., `delete_subject`, `delete_encounter`,
   `delete_record`).

If you intentionally grant Curator additional rights manually, do not re-run
`setup_curator_group` unless you also update that command to preserve the new policy.

**Warning:** Removing or adding user/group management or delete permissions may have
significant impact. Ensure this is intentional and auditable. See also
`archive/management/commands/setup_curator_group.py` source.
