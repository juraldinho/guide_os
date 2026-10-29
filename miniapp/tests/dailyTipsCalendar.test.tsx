import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { DayDetail } from '@/features/calendar/components/DayDetail';
import { CalendarOverlays } from '@/features/calendar/components/CalendarOverlays';
import { guideOsClient } from '@/api/createClient';
import { __resetMockStore } from '@/api/mock/store';

function Probe() {
  const { openDayDetail } = useCalendar();
  return <><button onClick={() => openDayDetail('1999-01-01')}>Выбрать дату</button><DayDetail /><CalendarOverlays /></>;
}
function setup() {
  render(<ToastProvider><CalendarProvider><Probe /></CalendarProvider></ToastProvider>);
  fireEvent.click(screen.getByText('Выбрать дату'));
}
async function open() {
  fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));
  expect(screen.getByRole('button', { name: 'Тур' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Выходной' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Чаевые' }));
  await screen.findByLabelText('Сумма, USD');
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); __resetMockStore(); });

it('chooser → save → updated day; edit, cancel and remove preserve date', async () => {
  setup();
  await open();
  fireEvent.change(screen.getByLabelText('Сумма, USD'), { target: { value: '25' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
  await screen.findByText('$25');
  expect(await guideOsClient.getDailyTip('1999-01-01')).toEqual({ date: '1999-01-01', amount: 25 });
  fireEvent.click(screen.getByText('Изменить чаевые'));
  expect(await screen.findByLabelText('Сумма, USD')).toHaveValue('25');
  fireEvent.change(screen.getByLabelText('Сумма, USD'), { target: { value: '90' } });
  fireEvent.click(screen.getByText('Отмена'));
  expect(await guideOsClient.getDailyTip('1999-01-01')).toMatchObject({ amount: 25 });
  fireEvent.click(screen.getByText('Изменить чаевые'));
  await screen.findByLabelText('Сумма, USD');
  fireEvent.change(screen.getByLabelText('Сумма, USD'), { target: { value: '0' } });
  fireEvent.click(screen.getByText('Сохранить'));
  await screen.findByText('Чаевые пока не добавлены.');
  expect(await guideOsClient.getDailyTip('1999-01-01')).toMatchObject({ amount: 0 });
});

it('validates, retains draft after failed save, prevents concurrent writes and retries', async () => {
  setup(); await open();
  const field = screen.getByLabelText('Сумма, USD');
  const save = vi.spyOn(guideOsClient, 'setDailyTip').mockRejectedValueOnce(new Error('offline'));
  fireEvent.change(field, { target: { value: '1.5' } });
  fireEvent.click(screen.getByText('Сохранить'));
  expect(screen.getByRole('alert')).toHaveTextContent('целое число');
  expect(save).not.toHaveBeenCalled();
  fireEvent.change(field, { target: { value: '40' } });
  fireEvent.click(screen.getByText('Сохранить'));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Не удалось сохранить'));
  expect(field).toHaveValue('40');
  let finish!: (value: { date: string; amount: number }) => void;
  save.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  fireEvent.click(screen.getByText('Сохранить'));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText('Сохранение…')).toBeDisabled();
  fireEvent.click(within(dialog).getByText('Сохранение…'));
  expect(save).toHaveBeenCalledTimes(2);
  finish({ date: '1999-01-01', amount: 40 });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});

it('retries a failed day load and editor load', async () => {
  const get = vi.spyOn(guideOsClient, 'getDailyTip').mockRejectedValue(new Error('offline'));
  setup();
  await screen.findByText('Не удалось загрузить чаевые.');
  get.mockRestore();
  fireEvent.click(screen.getByText('Повторить'));
  await screen.findByText('Чаевые пока не добавлены.');
  const editorGet = vi.spyOn(guideOsClient, 'getDailyTip').mockRejectedValue(new Error('offline'));
  fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));
  fireEvent.click(screen.getByRole('button', { name: 'Чаевые' }));
  const dialog = screen.getByRole('dialog');
  await within(dialog).findByText('Не удалось загрузить чаевые.');
  expect(within(dialog).queryByText('Сохранить')).not.toBeInTheDocument();
  editorGet.mockRestore();
  fireEvent.click(within(dialog).getByText('Повторить'));
  await within(dialog).findByLabelText('Сумма, USD');
});
