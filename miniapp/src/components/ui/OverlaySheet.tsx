import type { ReactNode } from 'react';
import { IconClose } from './Icons';

interface SheetProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  center?: boolean;
}

export function OverlaySheet({ title, onClose, children, footer, center }: SheetProps) {
  const overlayClass = center ? 'overlay center' : 'overlay';

  return (
    <div
      className={overlayClass}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="sheet">
        <div className="sheet-header">
          <span className="sheet-title">{title}</span>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Закрыть">
            <IconClose />
          </button>
        </div>
        <div className="sheet-body">{children}</div>
        {footer && <div className="sheet-footer">{footer}</div>}
      </div>
    </div>
  );
}
