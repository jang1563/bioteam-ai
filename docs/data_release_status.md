# Data Release Status

The BioTeam-AI code release and the project datasets have separate publication
decisions.

| Artifact | Status | Reason |
|---|---|---|
| BioTeam-AI source code | Public release candidate | MIT-licensed code and synthetic fixtures only |
| ContradictBio-338 | `not_published_pending_license` | Contains biomedical abstract text; redistribution and annotation review required |
| ContradictBio-1138 | `not_published_pending_license` | Contains biomedical abstract text; redistribution, provenance, and annotation review required |
| LitQA2 local cache | Not distributed | Third-party benchmark content is fetched or supplied under its own terms |

The private Hugging Face working repositories are not public release sources.
Their earlier card licenses must not be interpreted as relicensing third-party
abstract text.

Before either ContradictBio dataset is published, the release process must:

1. establish per-source redistribution rights or remove protected text;
2. preserve source identifiers and provenance without copying restricted text;
3. document the human and model annotation process;
4. rerun label-consistency and duplication checks;
5. create a clean dataset repository history and an explicit dataset license;
6. bind the exported artifact to a source commit and content hashes.

Until all six checks pass, the dataset status remains private and does not block
publication of the source-code repository.
