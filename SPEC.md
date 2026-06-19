# Orbital Streaming Protocol Secure (OSPS) Specification

## Status and scope

This document specifies the behavior implemented by OSPS 0.2 as demonstrated in
the North Star lab. OSPS is an experimental hobby protocol for simulating AI
workload transfer across intermittent orbital contacts. It is not an Internet
standard, a CCSDS standard, or a production replacement for the Bundle Protocol.

The key words MUST, SHOULD, and MAY describe current implementation
requirements, not standards-body consensus.

## 1. Entities and service

An endpoint is either the simulated ground station or satellite node. An
endpoint accepts application messages classified as `CONTROL`, `INFERENCE`,
`RESULT`, `TELEMETRY`, or `MODEL`. It chunks messages, queues them while links
are unavailable, and resumes transmission during later contacts.

The scheduler supplies contacts as a name, start time, duration, bandwidth,
latency, loss rate, and optional forced interruption. Contacts MAY be explicit
test data or generated from offline TLEs by Skyfield. The protocol endpoint
interface is identical in both cases.

## 2. Session establishment

Endpoint state is one of `DISCONNECTED`, `HELLO_SENT`,
`CHALLENGE_RECEIVED`, `AUTH_SENT`, or `ESTABLISHED`.

At contact opening, the initiator derives a 16-byte nonce from SHA-256 over its
name, peer name, and simulation tick. It produces HMAC-SHA256 over:

```text
nonce || initiator-name || responder-name
```

The responder verifies this value using the pre-shared key. The exchange is
then repeated in the reverse direction. Both endpoints enter `ESTABLISHED`
only after successful mutual verification. The simulator performs this
exchange directly; although control frame type codes exist, handshake messages
are not currently serialized through the link model.

Contact closure returns both endpoints to `DISCONNECTED` but MUST NOT erase
message, chunk, ACK, retry, or reassembly state.

## 3. Frame format

All serialized frames use network byte order:

```text
0                   1                   2                   3
+-------------------+-------------------+-------------------+
| Magic "NSTR" (4 bytes)                                   |
+--------+--------+--------+--------+-----------------------+
|Version | Type   | Flags  |Reserved| Stream ID (32 bits)   |
+--------+--------+--------+--------+-----------------------+
| Sequence (32 bits)               | Payload length (32)    |
+-----------------------------------------------------------+
| Payload (variable)                                        |
+-----------------------------------------------------------+
| HMAC-SHA256 tag, truncated to 16 bytes                    |
+-----------------------------------------------------------+
```

Version is `1`. Types are `HELLO=1`, `CHALLENGE=2`, `AUTH=3`, `DATA=4`,
`ACK=5`, and `ERROR=6`. Only `DATA` and `ACK` cross the simulated link today.
Flag bit 0 indicates encrypted payload. Other flag bits are not defined.

The integrity tag is computed over header and transmitted payload. Frames with
bad magic, unsupported version, inconsistent length, unknown type, or invalid
tag MUST be rejected.

## 4. Payload protection

After establishment, payload bytes are XORed with a stream generated from
HMAC-SHA256 keyed by the PSK and parameterized by stream ID, sequence, and a
counter. The tag authenticates the resulting frame.

This construction exists only to exercise encryption and authentication
boundaries. It has no protocol negotiation, key rotation, forward secrecy, or
security review and MUST NOT be used outside the simulation.

## 5. Messages, chunks, and scheduling

Each message receives a local 32-bit stream ID and is divided according to the
configured chunk size. Every DATA payload is compact JSON containing workload
name, total chunk count, and hex-encoded chunk bytes. Sequence numbers begin at
zero.

Priority order is:

1. control;
2. inference and result;
3. telemetry;
4. model.

FIFO order applies within each class. After a configurable burst of high
priority selections, the queue serves an available lower-priority stream to
limit starvation.

The sender schedules at most its congestion-window number of eligible chunks
per tick and never exceeds the contact byte budget. The congestion window
starts at one chunk, grows by one for each newly acknowledged chunk up to 16,
and halves on simulated loss with a minimum of one.

## 6. ACK, retry, and reassembly

Every DATA chunk requires an ACK carrying the same stream ID and sequence
number. The receiver stores chunks by these values. Duplicate DATA is harmless
and generates another ACK. Once all advertised chunks are present, the
receiver concatenates them in sequence order.

An unacknowledged chunk becomes eligible again after `retry_timeout` simulation
ticks. Each transmission increments its attempt count. Reaching `max_retries`
marks the stream failed. ACKed chunks are not retransmitted. This state
survives contact interruption, providing North Star lab store-and-forward
behavior between successive passes.

## 7. Relationship to CCSDS/DTN Bundle Protocol

The Bundle Protocol is a store-carry-forward overlay for stressed networks. A
Bundle Protocol Agent moves self-contained application data units called
bundles through one or more underlying networks using convergence-layer
adapters. Persistent retention permits forwarding to wait for scheduled,
predicted, or opportunistic connectivity.

Classic BPv6 custody transfer allowed an intermediate node to accept
responsibility for retaining and, if necessary, retransmitting a bundle until
another custodian accepted it, delivery was reported, or the bundle expired.
BPv7 moved custody-transfer functionality out of the core specification toward
bundle-in-bundle encapsulation. OSPS implements neither form: its ACK only
confirms one adjacent simulated peer received one chunk.

| Area | OSPS | CCSDS/DTN BP |
|---|---|---|
| Role | Direct two-endpoint streaming experiment | Multi-network overlay layer |
| Data unit | JSON chunk inside a fixed frame | Self-contained bundle made of blocks |
| Addressing | Local peer names and stream IDs | Endpoint IDs and node IDs |
| Storage | In-memory outbound and reassembly state | Persistent bundle retention model |
| Forwarding | Ground-to-satellite pair only | Multi-hop forwarding through BP agents |
| Contacts | Skyfield-predicted or configured | Scheduled, predicted, opportunistic, or continuous |
| Reliability | Per-chunk ACK and timeout retry | Convergence-layer reliability; BP processing and optional extensions |
| Custody | None | BPv6 custody; moved outside BPv7 core |
| Lifetime | None | Bundle lifetime, age, expiration, deletion |
| Fragmentation | Fixed source chunking | Protocol fragmentation and ADU reassembly |
| Extensibility | Version/type fields only | Canonical extension blocks and administrative records |
| Security | Educational PSK cipher and frame HMAC | BPSec block integrity/confidentiality plus secure convergence layers |
| Congestion | Small reactive chunk window | Convergence-layer rate limiting/congestion control |

OSPS diverges to keep protocol mechanics observable in the North Star lab's
small Python simulation. Its session handshake, strict workload priority,
adjacent ACKs, and single-hop assumptions are convenient for experimentation
but unsuitable for production space networking.

## 8. Minimum changes toward BP compatibility

1. Replace OSPS messages with BPv7 bundles encoded as CBOR, including primary
   and payload blocks, endpoint IDs, creation time, and lifetime.
2. Separate the bundle agent from a convergence-layer adapter; treat the
   current framed link as one possible adapter.
3. Persist bundles, retention state, duplicate detection, and reassembly across
   process restarts.
4. Add contact-aware multi-hop routing and forwarding decisions.
5. Implement status reports, expiration, extension-block processing, and BPv7
   fragmentation semantics.
6. Replace custom security with BPSec and an audited adjacent-link security
   mechanism.
7. Use an interoperable BP implementation and conformance vectors rather than
   evolving the current wire format into a competing near-BP protocol.

## References

- [CCSDS 734.2-B-1, *CCSDS Bundle Protocol Specification*](https://public.ccsds.org/Pubs/734x2b1.pdf).
- [IETF RFC 9171, *Bundle Protocol Version 7*](https://www.rfc-editor.org/rfc/rfc9171.html).
- [IETF RFC 9172, *Bundle Protocol Security (BPSec)*](https://www.rfc-editor.org/rfc/rfc9172.html).
- [IETF RFC 5050, *Bundle Protocol Specification*](https://www.rfc-editor.org/rfc/rfc5050.html)
  (BPv6, historical).
