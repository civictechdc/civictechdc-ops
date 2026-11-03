# Event-template drafts

**For human editing and approval; do not submit these files to an API.**

| File | Draft type |
| --- | --- |
| `project-night.json` | Collaborative project night |
| `workshop.json` | Hands-on workshop |
| `hackathon.json` | Build event |
| `showcase.json` | Project demos |
| `panel-networking.json` | Discussion and networking |

All descriptions, dates, venues, capacities, and schedules use placeholders.
JSON syntax validity does not establish API validity. Fields such as
`REPLACE_MAX_CAPACITY` are intentionally not schema-ready values, and
`_template_notes` is local metadata, not an API field.

Before any separately approved event creation:

1. Confirm the exact future date, start/end time, and timezone conversion,
   including daylight-saving transition ambiguity.
2. Confirm venue booking, place ID, accessibility, capacity, program, speakers,
   contacts, links, and any food or support commitments.
3. Replace every placeholder with approved content. Do not invent past
   achievements or imply an unconfirmed partnership.
4. Review registration questions for necessity, consent, privacy, and retention.
   Do not put participant responses in this repository.
5. Confirm visibility, guest-list privacy, and notification behavior. Drafts
   suggest private visibility, hidden guest lists, and disabled reminders;
   these settings do not guarantee all platform notifications are suppressed.
6. Verify the current creation schema and remove local metadata using a
   separately reviewed preparation process.
7. Obtain approval of the exact event and any messages before using a
   separately authorized write-capable tool.

The helper in this repository cannot create events. No template is a venue
booking, approved schedule, privacy guarantee, or authorization to contact people.
