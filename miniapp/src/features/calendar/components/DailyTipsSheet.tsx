import { useEffect, useRef, useState } from 'react';
import { guideOsClient } from '@/api/createClient';
import { MAX_DAILY_TIPS } from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { useCalendar } from '../CalendarContext';
import { fmtDateLong } from '../lib/dates';

function useDailyAmount() {
  const { selectedDate, tipsRevision } = useCalendar();
  const [amount, setAmount] = useState<number | null>(null);
  const [error, setError] = useState(false);
  const [attempt, retry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setAmount(null);
    setError(false);
    guideOsClient.getDailyTip(selectedDate).then((tip) => {
      if (!cancelled) setAmount(tip.amount);
    }).catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [selectedDate, tipsRevision, attempt]);
  return { amount, error, retry: () => retry((n) => n + 1) };
}

export function DailyTipsDay() {
  const { openTipsForm } = useCalendar();
  const { amount, error, retry } = useDailyAmount();
  return (
    <section className="day-detail-entry" aria-label="Чаевые за день">
      <div className="entry-title">Чаевые за день</div>
      {error ? <><p role="alert">Не удалось загрузить чаевые.</p><button className="btn btn-secondary" onClick={retry}>Повторить</button></> :
        amount === null ? <p role="status">Загрузка чаевых…</p> : <>
          <p>{amount > 0 ? `$${amount}` : 'Чаевые пока не добавлены.'}</p>
          <button type="button" className="btn btn-secondary" onClick={openTipsForm}>{amount > 0 ? 'Изменить чаевые' : 'Добавить чаевые'}</button>
        </>}
    </section>
  );
}

export function DailyTipsSheet() {
  const { selectedDate, closeOverlay, tipsChanged } = useCalendar();
  const { amount, error: loadError, retry } = useDailyAmount();
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const locked = useRef(false);
  const root = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    return () => { if (previous?.isConnected) previous.focus(); };
  }, []);
  useEffect(() => {
    if (amount !== null) { setInput(String(amount)); field.current?.focus(); }
  }, [amount]);

  const close = () => { if (!locked.current) closeOverlay(); };
  const save = async () => {
    if (locked.current || amount === null) return;
    if (!/^\d+$/.test(input) || !Number.isSafeInteger(Number(input)) || Number(input) > MAX_DAILY_TIPS) {
      setError(`Введите целое число USD от 0 до ${MAX_DAILY_TIPS}.`);
      field.current?.focus();
      return;
    }
    locked.current = true;
    setSaving(true);
    setError('');
    try {
      await guideOsClient.setDailyTip(selectedDate, Number(input));
      tipsChanged();
      closeOverlay();
    } catch {
      setError('Не удалось сохранить чаевые. Повторите попытку.');
    } finally {
      locked.current = false;
      setSaving(false);
    }
  };
  return (
    <div ref={root} role="dialog" aria-modal="true" aria-label="Чаевые за день" onKeyDown={(event) => {
      if (event.key === 'Escape') { event.stopPropagation(); close(); }
      if (event.key === 'Tab') {
        const elements = root.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)');
        if (!elements?.length) return;
        const first = elements[0], last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }}>
      <OverlaySheet title="Чаевые за день" onClose={close}>
        <p>{fmtDateLong(selectedDate)}</p>
        {loadError ? <><p role="alert">Не удалось загрузить чаевые.</p><button className="btn btn-secondary" onClick={retry}>Повторить</button></> :
          amount === null ? <p role="status">Загрузка чаевых…</p> : <form style={{ paddingBottom: 'var(--safe-bottom)' }} onSubmit={(event) => { event.preventDefault(); void save(); }}>
            <div className="form-group">
              <label className="form-label" htmlFor="daily-tips-amount">Сумма, USD</label>
              <input ref={field} id="daily-tips-amount" className="form-input" inputMode="numeric" value={input} disabled={saving}
                aria-invalid={!!error} aria-describedby="daily-tips-hint daily-tips-error"
                onChange={(event) => setInput(event.target.value)} />
            </div>
            <p id="daily-tips-hint" className="text-muted">Сохранение заменит общую сумму за день. Введите 0, чтобы удалить чаевые.</p>
            <p id="daily-tips-error" role={error ? 'alert' : undefined}>{error}</p>
            <button type="submit" className="btn btn-primary btn-block" disabled={saving}>{saving ? 'Сохранение…' : 'Сохранить'}</button>
            <button type="button" className="btn btn-secondary btn-block" style={{ marginTop: 8 }} disabled={saving} onClick={close}>Отмена</button>
          </form>}
      </OverlaySheet>
    </div>
  );
}
