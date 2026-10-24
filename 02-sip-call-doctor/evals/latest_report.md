# Detection eval report

Synthetic labeled captures. Measures designed behavior, not accuracy on real traffic.

**Exact matches:** 10/10 · **Root-cause accuracy:** 100% · **False positives:** 0 · **False negatives:** 0

| Capture | Expected | Found | Root cause | Result |
|---|---|---|---|---|
| `healthy_call` | — | — | — | PASS |
| `nat_one_way_audio` | media_to_private_address, nat_private_sdp | media_to_private_address, nat_private_sdp | media_to_private_address | PASS |
| `one_way_firewall` | one_way_audio | one_way_audio | one_way_audio | PASS |
| `codec_mismatch` | codec_mismatch | codec_mismatch | codec_mismatch | PASS |
| `auth_failure` | auth_failure | auth_failure | auth_failure | PASS |
| `setup_timeout` | large_udp_sip, setup_timeout | large_udp_sip, setup_timeout | setup_timeout | PASS |
| `poor_quality` | rtp_jitter, rtp_packet_loss | rtp_jitter, rtp_packet_loss | rtp_packet_loss | PASS |
| `busy_486` | call_rejected | call_rejected | call_rejected | PASS |
| `register_auth_failure` | auth_failure | auth_failure | auth_failure | PASS |
| `caller_cancelled` | — | — | — | PASS |

| Signature | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| `auth_failure` | 2 | 0 | 0 | 1.00 | 1.00 |
| `codec_mismatch` | 1 | 0 | 0 | 1.00 | 1.00 |
| `setup_timeout` | 1 | 0 | 0 | 1.00 | 1.00 |
| `call_rejected` | 1 | 0 | 0 | 1.00 | 1.00 |
| `nat_private_sdp` | 1 | 0 | 0 | 1.00 | 1.00 |
| `media_to_private_address` | 1 | 0 | 0 | 1.00 | 1.00 |
| `one_way_audio` | 1 | 0 | 0 | 1.00 | 1.00 |
| `rtp_packet_loss` | 1 | 0 | 0 | 1.00 | 1.00 |
| `rtp_jitter` | 1 | 0 | 0 | 1.00 | 1.00 |
| `large_udp_sip` | 1 | 0 | 0 | 1.00 | 1.00 |
