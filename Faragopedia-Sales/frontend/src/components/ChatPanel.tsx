import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { API_BASE } from '../config';

interface Props {
  className?: string;
  onLinkClick?: (path: string) => void;
  showHeader?: boolean;
}

const ChatPanel: React.FC<Props> = ({ className = '', onLinkClick, showHeader = true }) => {
  const [chatQuery, setChatQuery] = useState('');
  const [chatHistory, setChatHistory] = useState<{ id: number, role: 'user' | 'assistant', content: string }[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, chatLoading]);

  const handleChat = async () => {
    if (!chatQuery.trim()) return;
    const userMessage = chatQuery;
    setChatQuery('');
    setChatHistory(prev => [...prev, { id: Date.now(), role: 'user', content: userMessage }]);
    setChatLoading(true);
    try {
      const response = await fetch(`${API_BASE}/chat?query=${encodeURIComponent(userMessage)}`, { method: 'POST' });
      if (!response.ok) throw new Error('Chat failed');
      const data = await response.json();
      setChatHistory(prev => [...prev, { id: Date.now(), role: 'assistant', content: data.response }]);
    } catch (err) {
      setChatHistory(prev => [...prev, { id: Date.now(), role: 'assistant', content: 'Sorry, I encountered an error.' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const processChatLinks = (text: string) => {
    return text.replace(/\[\[(.*?)\]\]/g, (match, p1) => {
      const [rawPath, rawAlias] = p1.split('|');
      // The LLM is inconsistent about including the .md extension in the
      // wikilink itself — strip it here so the anchor never doubles it up.
      const path = rawPath.trim().replace(/\.md$/i, '');
      const alias = rawAlias?.trim();
      const slug = path.toLowerCase().replace(/\s+/g, '-');
      if (path.includes('/')) {
        const label = alias || path.split('/').pop()?.replace(/-/g, ' ');
        return `[${label}](#${path.replace(/\//g, '__')})`;
      }
      return `[${alias || path}](#${slug})`;
    });
  };

  return (
    <div className={`flex flex-col bg-white h-full ${className}`}>
      {showHeader && (
        <div className="border-b px-4 h-16 bg-white/80 backdrop-blur-sm z-10 flex items-center justify-between shrink-0">
          <h2 className="font-bold text-gray-800 flex items-center">
            <MessageSquare className="w-5 h-5 mr-2" /> AI Assistant
          </h2>
        </div>
      )}
      <div className="flex-grow overflow-y-auto p-4 space-y-4">
        {chatHistory.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-gray-400 space-y-4 text-center">
            <MessageSquare className="w-8 h-8 opacity-20" />
            <p className="text-sm">Start a conversation with your Wiki</p>
          </div>
        ) : (
          chatHistory.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[90%] px-5 py-3 rounded-2xl ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-none'
                  : 'bg-gray-100 text-gray-800 rounded-tl-none prose prose-sm prose-slate max-w-none'
              }`}>
                {msg.role === 'user' ? (
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    className="text-sm leading-relaxed whitespace-pre-wrap"
                    components={{
                      a: ({ node, ...props }) => {
                        const isInternal = props.href?.startsWith('#');
                        if (isInternal) {
                          return (
                            <a
                              {...props}
                              onClick={(e) => {
                                e.preventDefault();
                                if (onLinkClick) {
                                  const ref = props.href?.slice(1);
                                  const pagePath = ref?.replace('__', '/') + '.md';
                                  onLinkClick(pagePath);
                                }
                              }}
                              className="text-blue-600 hover:underline font-medium cursor-pointer"
                            >
                              {props.children}
                            </a>
                          );
                        }
                        return (
                          <a {...props} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer" />
                        );
                      }
                    }}
                  >
                    {processChatLinks(msg.content)}
                  </ReactMarkdown>
                )}
              </div>
            </div>
          ))
        )}
        {chatLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 px-5 py-3 rounded-2xl rounded-tl-none flex items-center space-x-2">
              <Loader2 className="w-4 h-4 animate-spin text-gray-500" />
            </div>
          </div>
        )}
        <div ref={chatBottomRef} />
      </div>
      <div className="p-3 bg-gray-50 border-t shrink-0">
        <div className="relative">
          <input
            type="text"
            value={chatQuery}
            onChange={(e) => setChatQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleChat()}
            placeholder="Ask a question..."
            disabled={chatLoading}
            className="w-full px-4 py-2 pr-10 bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-sm"
          />
          <button
            onClick={handleChat}
            disabled={chatLoading || !chatQuery.trim()}
            className="absolute right-1.5 top-1.5 bg-blue-600 text-white p-1.5 rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
