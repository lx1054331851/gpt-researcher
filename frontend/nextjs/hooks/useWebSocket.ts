import { useRef, useState, useEffect, useCallback } from 'react';
import { Data, ChatBoxSettings, OutlineDraftData, OutlineUpdatedData } from '../types/data';
import { getHost } from '../helpers/getHost';

const ABSOLUTE_URL_PATTERN = /^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//;

const buildWebSocketUrl = (hostOrUrl: string): string => {
  const trimmedHost = hostOrUrl.trim();
  if (!trimmedHost) {
    return 'ws://localhost:8000/ws';
  }

  const normalizedUrl = ABSOLUTE_URL_PATTERN.test(trimmedHost)
    ? trimmedHost
    : `http://${trimmedHost}`;

  try {
    const parsedUrl = new URL(normalizedUrl);
    const protocol =
      parsedUrl.protocol === 'https:' || parsedUrl.protocol === 'wss:' ? 'wss:' : 'ws:';
    const cleanPath = parsedUrl.pathname.replace(/\/+$/, '');
    const pathPrefix = cleanPath === '/' ? '' : cleanPath;

    return `${protocol}//${parsedUrl.host}${pathPrefix}/ws`;
  } catch (error) {
    console.warn(`Invalid host for WebSocket: ${hostOrUrl}. Falling back to localhost:8000.`);
    return 'ws://localhost:8000/ws';
  }
};

export const useWebSocket = (
  setOrderedData: React.Dispatch<React.SetStateAction<Data[]>>,
  setAnswer: React.Dispatch<React.SetStateAction<string>>, 
  setLoading: React.Dispatch<React.SetStateAction<boolean>>,
  setShowHumanFeedback: React.Dispatch<React.SetStateAction<boolean>>,
  setQuestionForHuman: React.Dispatch<React.SetStateAction<boolean | true>>,
  options?: {
    onOutlineDraft?: (data: OutlineDraftData) => void;
    onOutlineUpdated?: (data: OutlineUpdatedData) => void;
  }
) => {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const heartbeatInterval = useRef<number>();

  // Cleanup function for heartbeat and socket on unmount
  useEffect(() => {
    return () => {
      // Clear heartbeat interval
      if (heartbeatInterval.current) {
        clearInterval(heartbeatInterval.current);
      }
      
      // Close socket on unmount if it exists and is open
      if (socket && socket.readyState === WebSocket.OPEN) {
        console.log('Closing WebSocket due to component unmount');
        socket.close(1000, "Component unmounted");
      }
    };
  }, [socket]);

  const startHeartbeat = (ws: WebSocket) => {
    // Clear any existing heartbeat
    if (heartbeatInterval.current) {
      clearInterval(heartbeatInterval.current);
    }
    
    // Start new heartbeat
    heartbeatInterval.current = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 30000); // Send ping every 30 seconds
  };

  const initializeWebSocket = useCallback((
    promptValue: string, 
    chatBoxSettings: ChatBoxSettings
  ) => {
    // Close existing socket if any
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log('Closing existing WebSocket connection');
      socket.close(1000, "New connection requested");
    }

    if (typeof window !== 'undefined') {
      const ws_uri = buildWebSocketUrl(getHost());

      console.log(`Creating new WebSocket connection to ${ws_uri}`);
      const newSocket = new WebSocket(ws_uri);
      setSocket(newSocket);

      // WebSocket connection opened handler
      newSocket.onopen = () => {
        console.log('WebSocket connection opened');
        
        const domainFilters = JSON.parse(localStorage.getItem('domainFilters') || '[]');
        const domains = domainFilters ? domainFilters.map((domain: any) => domain.value) : [];
        const {
          report_type,
          report_source,
          tone,
          report_language,
          report_style,
          source_policy,
          word_fonts,
          mcp_enabled,
          mcp_configs,
          mcp_strategy,
        } = chatBoxSettings;
        
        // Start a new research
        try {
          console.log(`Starting new research for: ${promptValue}`);
          const dataToSend = { 
            task: promptValue,
            report_type, 
            report_source, 
            tone,
            language: report_language || "chinese",
            report_style: report_style || "strategic_report",
            source_policy: source_policy || "medium_tier",
            word_fonts: word_fonts?.length ? word_fonts : ["仿宋", "FangSong", "STFangsong"],
            query_domains: domains,
            mcp_enabled: mcp_enabled || false,
            mcp_strategy: mcp_strategy || "fast",
            mcp_configs: mcp_configs || []
          };
          
          const command = report_type === 'adaptive_deep' ? 'start_plan' : 'start';
          const message = `${command} ${JSON.stringify(dataToSend)}`;
          console.log(`Sending start message, length: ${message.length}`);
          newSocket.send(message);
        } catch (error) {
          console.error("Error preparing start message:", error);
        }
        
        startHeartbeat(newSocket);
      };

      newSocket.onmessage = (event) => {
        try {
          // Handle ping response
          if (event.data === 'pong') return;

          // Try to parse JSON data
          console.log(`Received WebSocket message: ${event.data.substring(0, 100)}...`);
          const data = JSON.parse(event.data);
          
          if (data.type === 'error') {
            console.error(`Server error: ${data.output}`);
            setLoading(false);
            const contentAndType = `${data.content}-${data.type}`;
            setOrderedData((prevOrder) => [...prevOrder, { ...data, contentAndType }]);
          } else if (data.type === 'outline_validation_error') {
            console.warn(`Outline validation error: ${data.output}`);
            setLoading(false);
            const contentAndType = `${data.content}-${data.type}`;
            setOrderedData((prevOrder) => [...prevOrder, { ...data, contentAndType }]);
          } else if (data.type === 'human_feedback' && data.content === 'request') {
            setQuestionForHuman(data.output);
            setShowHumanFeedback(true);
          } else {
            const contentAndType = `${data.content}-${data.type}`;
            setOrderedData((prevOrder) => [...prevOrder, { ...data, contentAndType }]);

            if (data.type === 'outline_draft') {
              setLoading(false);
              options?.onOutlineDraft?.(data as OutlineDraftData);
            } else if (data.type === 'outline_updated') {
              setLoading(false);
              options?.onOutlineUpdated?.(data as OutlineUpdatedData);
            } else if (data.type === 'report') {
              setAnswer((prev: string) => prev + data.output);
            } else if (data.type === 'report_complete') {
              // Replace entire report with the complete version (includes images)
              console.log('Received complete report with images');
              setAnswer(data.output);
            } else if (data.type === 'path') {
              setLoading(false);
            }
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error, event.data);
        }
      };

      newSocket.onclose = (event) => {
        console.log(`WebSocket connection closed: code=${event.code}, reason=${event.reason}`);
        if (heartbeatInterval.current) {
          clearInterval(heartbeatInterval.current);
        }
        setSocket(null);
      };

      newSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        if (heartbeatInterval.current) {
          clearInterval(heartbeatInterval.current);
        }
      };
    }
  }, [options, socket, setOrderedData, setAnswer, setLoading, setShowHumanFeedback, setQuestionForHuman]);

  const revisePlan = useCallback(
    (payload: Record<string, unknown>) => {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        console.warn("WebSocket is not open; cannot send revise_plan");
        return false;
      }
      socket.send(`revise_plan ${JSON.stringify(payload)}`);
      setLoading(true);
      return true;
    },
    [setLoading, socket]
  );

  const executePlan = useCallback(
    (payload: Record<string, unknown>) => {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        console.warn("WebSocket is not open; cannot send execute_plan");
        return false;
      }
      socket.send(`execute_plan ${JSON.stringify(payload)}`);
      setLoading(true);
      return true;
    },
    [setLoading, socket]
  );

  return { socket, setSocket, initializeWebSocket, revisePlan, executePlan };
};
