import React, { useEffect } from 'react';

interface ErrorToastProps {
  message: string;
  onDismiss: () => void;
}

const ErrorToast: React.FC<ErrorToastProps> = ({ message, onDismiss }) => {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 5000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  return (
    <div
      role="alert"
      className="fixed bottom-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded flex items-center gap-3 shadow-lg max-w-sm"
    >
      <span className="text-sm">{message}</span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="ml-auto text-red-700 hover:text-red-900 font-bold text-lg leading-none"
      >
        &times;
      </button>
    </div>
  );
};

export default ErrorToast;
