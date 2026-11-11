import React, { useState } from 'react';
import { MoveRight } from 'lucide-react';

const ENTITY_TYPES = ['clients', 'contacts', 'photographers', 'productions', 'prospects'] as const;
type EntityType = typeof ENTITY_TYPES[number];

type Props = {
  selectedCount: number;
  initialDestination?: EntityType;
  onConfirm: (destination: EntityType) => void;
  onClose: () => void;
};

const MoveDialog: React.FC<Props> = ({ selectedCount, initialDestination, onConfirm, onClose }) => {
  const [destination, setDestination] = useState<EntityType>(initialDestination ?? 'clients');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4 animate-fade-in border border-gray-100">
        <h2 className="text-gray-900 font-semibold text-base mb-1">Move {selectedCount} page{selectedCount !== 1 ? 's' : ''}</h2>
        <p className="text-gray-500 text-sm mb-5">Select a destination entity type.</p>
        <div className="flex flex-col gap-2 mb-6">
          {ENTITY_TYPES.map((type) => (
            <label
              key={type}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer border transition-all ${
                destination === type
                  ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium'
                  : 'border-gray-200 hover:bg-gray-50 text-gray-700'
              }`}
            >
              <input
                type="radio"
                name="destination"
                value={type}
                checked={destination === type}
                onChange={() => setDestination(type)}
                className="accent-blue-600"
              />
              <span className="capitalize text-sm">{type}</span>
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors font-medium"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(destination)}
            className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-500 transition-colors font-bold"
          >
            <MoveRight className="w-4 h-4" />
            Move {selectedCount} page{selectedCount !== 1 ? 's' : ''}
          </button>
        </div>
      </div>
    </div>
  );
};

export default MoveDialog;
