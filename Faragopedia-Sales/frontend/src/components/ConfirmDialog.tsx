import React from 'react';

type Props = {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
};

const ConfirmDialog: React.FC<Props> = ({ message, onConfirm, onCancel, confirmLabel = 'Confirm' }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
    <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4 animate-fade-in border border-gray-100">
      <p className="text-gray-800 text-base mb-6 leading-relaxed">{message}</p>
      <div className="flex justify-end gap-3">
        <button
          onClick={onCancel}
          className="px-4 py-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-all text-sm font-medium"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className="px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 shadow-md hover:shadow-lg transition-all text-sm font-medium"
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  </div>
);

export default ConfirmDialog;
