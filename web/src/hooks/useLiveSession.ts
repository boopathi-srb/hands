import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import {
  appendHumanAction,
  clickMessage,
  keyEventToMessage,
  parseServerMessage,
  scaleClickToFrame,
  type HumanActionView,
  type KeyLike,
  type ServerMessage,
} from '../lib/liveInput'

export type LiveStatus = 'idle' | 'connecting' | 'live' | 'closed' | 'refused'

export interface LiveSession {
  status: LiveStatus
  message: string | null
  actions: HumanActionView[]
  hasFrame: boolean
  canvasRef: RefObject<HTMLCanvasElement | null>
  connect: (url: string) => void
  disconnect: () => void
  sendClick: (clientX: number, clientY: number) => void
  sendKey: (event: KeyLike, phase: 'down' | 'up') => void
}

/**
 * One operator live-view websocket: draws frames onto a canvas at the frame's native size, sends
 * pointer and key input in frame pixels, and records the actions the server accepted.
 */
export function useLiveSession(): LiveSession {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const [status, setStatus] = useState<LiveStatus>('idle')
  const [message, setMessage] = useState<string | null>(null)
  const [actions, setActions] = useState<HumanActionView[]>([])
  const [hasFrame, setHasFrame] = useState(false)

  const drawFrame = useCallback((mime: string, data: string) => {
    const image = imageRef.current ?? new Image()
    imageRef.current = image
    image.onload = () => {
      const canvas = canvasRef.current
      if (!canvas) return
      if (canvas.width !== image.naturalWidth) canvas.width = image.naturalWidth
      if (canvas.height !== image.naturalHeight) canvas.height = image.naturalHeight
      canvas.getContext('2d')?.drawImage(image, 0, 0)
      setHasFrame(true)
    }
    image.onerror = () => console.error('useLiveSession.drawFrame: frame could not be decoded', { mime, length: data.length })
    image.src = `data:${mime};base64,${data}`
  }, [])

  const handleMessage = useCallback(
    (serverMessage: ServerMessage) => {
      switch (serverMessage.type) {
        case 'frame':
          drawFrame(serverMessage.mime, serverMessage.data)
          return
        case 'connected':
          setStatus('live')
          setMessage('You are in control. Click the screen to focus it; clicks and keys go to the live session.')
          return
        case 'input_accepted':
          if (serverMessage.action) {
            const action = serverMessage.action
            setActions((previous) => appendHumanAction(previous, action))
          }
          return
        case 'input_rejected':
          setMessage(`Input rejected: ${serverMessage.message}`)
          return
        case 'control_lost':
          setMessage('Control returned; the live view is closing.')
          return
        case 'error':
          setStatus('refused')
          setMessage(`Live view refused: ${serverMessage.message}`)
          return
      }
    },
    [drawFrame],
  )

  const disconnect = useCallback(() => {
    socketRef.current?.close()
    socketRef.current = null
  }, [])

  const connect = useCallback(
    (url: string) => {
      disconnect()
      setStatus('connecting')
      setMessage('Connecting to the live session…')
      setActions([])
      setHasFrame(false)
      const socket = new WebSocket(url)
      socketRef.current = socket
      socket.onmessage = (event: MessageEvent) => {
        const parsed = typeof event.data === 'string' ? parseServerMessage(event.data) : null
        if (parsed) handleMessage(parsed)
      }
      socket.onerror = () => {
        console.error('useLiveSession: websocket error', { url: url.replace(/token=[^&]+/, 'token=***') })
        setMessage('The live view connection failed.')
      }
      socket.onclose = (event: CloseEvent) => {
        if (socketRef.current === socket) socketRef.current = null
        setStatus((previous) => (previous === 'refused' ? previous : 'closed'))
        if (event.code !== 1000 && event.reason) setMessage(`Live view closed: ${event.reason}`)
      }
    },
    [disconnect, handleMessage],
  )

  useEffect(() => disconnect, [disconnect])

  const send = useCallback((payload: unknown) => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return
    socket.send(JSON.stringify(payload))
  }, [])

  const sendClick = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current
      if (!canvas) return
      const point = scaleClickToFrame(clientX, clientY, canvas.getBoundingClientRect(), {
        width: canvas.width,
        height: canvas.height,
      })
      if (point) send(clickMessage(point))
    },
    [send],
  )

  const sendKey = useCallback(
    (event: KeyLike, phase: 'down' | 'up') => {
      const keyMessage = keyEventToMessage(event, phase)
      if (keyMessage) send(keyMessage)
    },
    [send],
  )

  return { status, message, actions, hasFrame, canvasRef, connect, disconnect, sendClick, sendKey }
}
