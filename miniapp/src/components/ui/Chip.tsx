interface ChipProps {
  label: string;
  active?: boolean;
  onClick?: () => void;
  disabled?: boolean;
}

export function Chip({ label, active, onClick, disabled }: ChipProps) {
  return (
    <button
      type="button"
      className={`chip${active ? ' active' : ''}`}
      onClick={onClick}
      disabled={disabled}
      style={disabled ? { opacity: 0.4 } : undefined}
    >
      {label}
    </button>
  );
}
