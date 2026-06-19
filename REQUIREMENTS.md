# North Star Requirements

## Problem statement

Orbital compute nodes have useful processing and storage capacity, but their
links to Earth are intermittent, delayed, bandwidth-limited, and occasionally
unreliable. HTTP assumes a comparatively stable end-to-end path. North Star
explores North Star, a session-oriented protocol
that can move AI workload data across repeated contact windows without losing
progress.

This repository is a hobby-grade protocol simulation. It tests protocol
behavior, not orbital physics or production cryptography.

## Goals

- Establish authenticated sessions between a ground station and satellite.
- Frame and chunk AI workload messages.
- Prioritize latency-sensitive traffic without permanently starving bulk data.
- Preserve queued and partially transferred messages between contact windows.
- Detect corruption/loss, acknowledge chunks, retry, and resume.
- Apply simple congestion control suited to a changing simulated link.
- Produce structured, readable evidence of protocol behavior.
- Keep components deterministic, extensible, and independently testable.

## Non-goals

- Accurate orbit, RF propagation, antenna, or weather simulation.
- A production-ready cryptographic implementation.
- Kernel networking, sockets, an HTTP replacement gateway, or standards work.
- Multi-hop routing, inter-satellite links, or distributed consensus.
- Efficient transfer of real model files.

## Actors

- **Ground station:** originates AI requests/uploads and receives results and
  telemetry.
- **Satellite node:** performs simulated orbital compute, stores messages, and
  transfers data whenever a contact window opens.
- **AI consumer:** an application represented by traffic submitted through the
  ground station.

## Assumptions

- Nodes share a pre-shared key (PSK).
- Simulation time advances in fixed ticks and is not wall-clock time.
- Each contact window defines duration, bandwidth, latency, and optional loss.
- Messages fit in local storage for the sample scenario.
- A transfer can resume at the first unacknowledged chunk in a later pass.
- Encryption is represented by a deterministic XOR stream plus HMAC-SHA256.
  This demonstrates boundaries and authentication but is not secure enough for
  real deployment. Production North Star would use an audited AEAD construction.

## Functional requirements

### Session handshake

- Nodes exchange `HELLO`, `CHALLENGE`, and `AUTH` control frames.
- Authentication uses HMAC-SHA256 over both node identities and a nonce.
- Data flows only after both peers reach `ESTABLISHED`.
- A new contact can resume an existing logical session.

### Message types and framing

- Workload classes: `INFERENCE`, `RESULT`, `TELEMETRY`, `MODEL`, and `CONTROL`.
- Every binary frame includes a magic value, version, type, flags, stream ID,
  sequence number, payload length, payload, and integrity tag.
- Unsupported versions, malformed lengths, and invalid tags are rejected.
- Large messages are split into independently acknowledged chunks.

### Priority and QoS

- Strict priority is used within each scheduling round:
  control, inference/results, telemetry, then model data.
- A configurable burst limit forces occasional service of lower-priority
  queues, preventing permanent starvation.
- FIFO order is preserved within a priority class.

### Store-and-forward

- Outbound messages remain in a durable-in-simulation queue while no link is
  available.
- Partial transfer state and ACK state survive closed or interrupted passes.
- Buffer limits are enforced and overflow is reported clearly.

### Congestion control

- Each session maintains a congestion window measured in chunks.
- Successful ACK rounds increase the window additively.
- Loss or timeout reduces the window multiplicatively.
- The contact's byte budget is always an upper bound.

### Errors, ACKs, and retries

- Every data chunk requires an ACK.
- Lost or corrupted chunks remain unacknowledged and are retried.
- Retries stop at a configurable maximum and produce a failed-message event.
- Duplicate chunks are safe and result in another ACK.

### Authentication and encryption

- A PSK authenticates the handshake and frames.
- Payloads are encrypted in the simulator after session establishment.
- Authentication failure closes the session and is logged.

## Non-functional requirements

- Python 3.11+ with Skyfield as the only direct third-party dependency.
- Deterministic scenarios when supplied with a random seed.
- Clear module boundaries between framing, queues, nodes, and simulation.
- Unit tests must not depend on wall-clock sleeps or external services.
- Protocol enums and frame versions permit future extension.
- Structured JSON-line logs must be machine-readable.

## Success criteria

Running the sample scenario with one command must:

1. authenticate a ground/satellite session;
2. transfer multiple workload classes in priority order;
3. close or interrupt a pass while a large model stream is incomplete;
4. retain the unacknowledged data;
5. reconnect during a later contact window and complete it;
6. print timestamps, events, bytes transferred, retry information, and queue
   state; and
7. pass unit tests for framing, priority behavior, and retransmission.

The live demonstration additionally succeeds only when two standalone endpoint
processes exchange a multi-megabyte file through a third pass-driven channel
process, reconnect across multiple predicted windows, and produce identical
sender/receiver SHA-256 digests using real wall-clock logs.
