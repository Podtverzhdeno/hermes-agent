# ACP approval hardening follow-up

ACP enforcement uses a dedicated execution-context flag; ambient noninteractive and YOLO settings must not silently grant a request in a guarded ACP scope. Existing container-backend exemptions, non-terminal tool paths and same-session concurrency require separate review before unattended execution. Changes here deliberately permit only one-time ACP approval and do not trust preexisting global pattern approvals.

Regression matrix: callback signature, interactive vs noninteractive, explicit missing connection, denied/unknown selection, global YOLO, mode=off, global stored approvals, multiple sessions and nested threads. CI must validate exact head SHA before merge.
