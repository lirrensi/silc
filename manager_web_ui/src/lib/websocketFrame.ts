// FILE: manager_web_ui/src/lib/websocketFrame.ts
// PURPOSE: Encode and decode SILC websocket frames for binary terminal transport.
// OWNS: Framed websocket serialization, parsing, and framed send helpers.
// EXPORTS: encodeWsFrame - build a binary frame; decodeWsFrame - parse a binary frame; sendInputFrame - send framed terminal input; requestHistoryFrame - request terminal history.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

const textEncoder = new TextEncoder()
const textDecoder = new TextDecoder()

export interface WsFrame {
  header: Record<string, unknown>
  payload: Uint8Array
}

export function encodeWsFrame(
  header: Record<string, unknown>,
  payload: Uint8Array = new Uint8Array(),
): Uint8Array {
  const headerBytes = textEncoder.encode(JSON.stringify(header))
  const frame = new Uint8Array(4 + headerBytes.length + payload.byteLength)
  const view = new DataView(frame.buffer)

  view.setUint32(0, headerBytes.length, false)
  frame.set(headerBytes, 4)
  frame.set(payload, 4 + headerBytes.length)

  return frame
}

export function decodeWsFrame(buffer: ArrayBuffer): WsFrame {
  if (buffer.byteLength < 4) {
    throw new Error('frame too short')
  }

  const view = new DataView(buffer)
  const headerLength = view.getUint32(0, false)
  if (buffer.byteLength < 4 + headerLength) {
    throw new Error('frame truncated')
  }

  const headerBytes = new Uint8Array(buffer, 4, headerLength)
  const payload = new Uint8Array(buffer, 4 + headerLength)

  let headerValue: unknown
  try {
    headerValue = JSON.parse(textDecoder.decode(headerBytes))
  } catch (err) {
    if (err instanceof SyntaxError) {
      throw new Error('invalid frame header json')
    }
    throw new Error('invalid frame header encoding')
  }

  if (!headerValue || typeof headerValue !== 'object' || Array.isArray(headerValue)) {
    throw new Error('frame header must be object')
  }

  return {
    header: headerValue as Record<string, unknown>,
    payload,
  }
}

export function sendWsFrame(
  ws: WebSocket,
  header: Record<string, unknown>,
  payload: Uint8Array = new Uint8Array(),
): void {
  ws.send(encodeWsFrame(header, payload).buffer as ArrayBuffer)
}

export function sendInputFrame(ws: WebSocket, text: string, nonewline: boolean = true): void {
  sendWsFrame(ws, { type: 'input', nonewline }, textEncoder.encode(text))
}

export function requestHistoryFrame(ws: WebSocket): void {
  sendWsFrame(ws, { type: 'load_history' })
}
