import { api } from './api.js';
import type { Layout, Schedule } from './types.js';
import { badge, emptyState, escapeHtml, icon, openDialog, pageHeader, skeleton, toast } from './ui.js';

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const errorText = (error: unknown): string => error instanceof Error ? error.message : String(error);

export async function renderSchedules(root: HTMLElement): Promise<void> {
  root.innerHTML = pageHeader('Schedules', 'Apply saved layouts automatically at the times you choose') + skeleton(4);
  const refresh = async (): Promise<void> => {
    const [schedules, layouts] = await Promise.all([api<Schedule[]>('/schedules'), api<Layout[]>('/layouts')]);
    root.innerHTML = `${pageHeader('Schedules', 'Apply saved layouts automatically at the times you choose', `<button id="add-schedule" class="button button-primary" ${layouts.length ? '' : 'disabled'}>${icon('plus')} New schedule</button>`)}
      <p class="schedule-help">Times use the appliance's system timezone; configure that timezone on the appliance. Overnight windows continue into the following day. Higher priority wins overlaps; when a window ends, the last applied layout stays on screen until another schedule or manual action changes it.</p>
      <section class="panel table-panel">${schedules.length ? `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Schedule</th><th>Layout</th><th>Days</th><th>Time</th><th>Priority</th><th>Status</th><th>Actions</th></tr></thead><tbody>${schedules.map((schedule) => `<tr><td><strong>${escapeHtml(schedule.name)}</strong></td><td>${escapeHtml(layouts.find((layout) => layout.id === schedule.layout_id)?.name ?? 'Missing layout')}</td><td>${schedule.days.map((day) => days[day]?.slice(0, 3)).join(', ')}</td><td>${escapeHtml(schedule.start_time)}–${escapeHtml(schedule.end_time)}${schedule.start_time > schedule.end_time ? ' (+1 day)' : schedule.start_time === schedule.end_time ? ' (24 hours)' : ''}</td><td>${schedule.priority}</td><td>${badge(schedule.enabled ? 'Enabled' : 'Disabled', schedule.enabled ? 'good' : 'neutral')}</td><td><div class="row-actions"><button class="button button-ghost button-small" data-toggle-schedule="${schedule.id}">${schedule.enabled ? 'Disable' : 'Enable'}</button><button class="icon-button" data-edit-schedule="${schedule.id}" aria-label="Edit ${escapeHtml(schedule.name)}">${icon('edit')}</button><button class="icon-button" data-delete-schedule="${schedule.id}" aria-label="Delete ${escapeHtml(schedule.name)}">${icon('trash')}</button></div></td></tr>`).join('')}</tbody></table></div>` : emptyState('display', 'No schedules yet', layouts.length ? 'Set a day or night wall, weekdays, or an overnight rotation layout.' : 'Create a layout before scheduling it.')}</section>`;
    root.querySelector('#add-schedule')?.addEventListener('click', () => scheduleDialog(null, layouts, refresh));
    root.querySelectorAll<HTMLButtonElement>('[data-edit-schedule]').forEach((button) => button.addEventListener('click', () => scheduleDialog(schedules.find((item) => item.id === button.dataset.editSchedule)!, layouts, refresh)));
    root.querySelectorAll<HTMLButtonElement>('[data-toggle-schedule]').forEach((button) => button.addEventListener('click', async () => {
      const schedule = schedules.find((item) => item.id === button.dataset.toggleSchedule)!;
      button.disabled = true;
      try { await api(`/schedules/${schedule.id}`, { method: 'PUT', body: JSON.stringify({ ...schedule, enabled: !schedule.enabled }) }); await refresh(); }
      catch (error) { toast(errorText(error), 'error'); button.disabled = false; }
    }));
    root.querySelectorAll<HTMLButtonElement>('[data-delete-schedule]').forEach((button) => button.addEventListener('click', async () => {
      if (!confirm('Delete this schedule?')) return;
      try { await api(`/schedules/${button.dataset.deleteSchedule}`, { method: 'DELETE' }); await refresh(); }
      catch (error) { toast(errorText(error), 'error'); }
    }));
  };
  try { await refresh(); } catch (error) { root.innerHTML = pageHeader('Schedules', 'Automatic layout changes') + emptyState('offline', 'Unable to load schedules', errorText(error)); }
}

function scheduleDialog(schedule: Schedule | null, layouts: Layout[], refresh: () => Promise<void>): void {
  openDialog({ title: schedule ? `Edit ${schedule.name}` : 'New schedule', submitLabel: 'Save schedule', body: `<div class="form-grid two">
    <label><span>Name</span><input class="input" name="name" required maxlength="255" value="${escapeHtml(schedule?.name ?? '')}" /></label>
    <label><span>Layout</span><select class="select" name="layout" required>${layouts.map((layout) => `<option value="${layout.id}" ${schedule?.layout_id === layout.id ? 'selected' : ''}>${escapeHtml(layout.name)}</option>`).join('')}</select></label>
    <label><span>Starts</span><input class="input" type="time" name="start" required value="${schedule?.start_time ?? '08:00'}" /></label>
    <label><span>Ends</span><input class="input" type="time" name="end" required value="${schedule?.end_time ?? '18:00'}" /></label>
    <label><span>Priority</span><input class="input" type="number" name="priority" min="-1000" max="1000" step="1" required value="${schedule?.priority ?? 0}" /></label>
    <label class="checkbox-row"><input type="checkbox" name="enabled" ${schedule?.enabled === false ? '' : 'checked'} /><span>Schedule enabled</span></label>
    <fieldset class="span-two"><legend>Starting days</legend><div class="day-choices">${days.map((day, index) => `<label><input type="checkbox" name="day" value="${index}" ${(schedule?.days ?? [0,1,2,3,4,5,6]).includes(index) ? 'checked' : ''} />${day}</label>`).join('')}</div></fieldset>
    <p class="form-help span-two">An end time earlier than the start continues into the next day. Equal times mean a full 24-hour window.</p>
    </div>`, onSubmit: async (dialog) => {
      const value = (name: string): string => dialog.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`)!.value;
      const selectedDays = [...dialog.querySelectorAll<HTMLInputElement>('[name="day"]:checked')].map((input) => Number(input.value));
      if (!selectedDays.length) { toast('Select at least one starting day', 'warning'); return false; }
      const payload = { name: value('name').trim(), layout_id: value('layout'), start_time: value('start'), end_time: value('end'), priority: Number(value('priority')), enabled: dialog.querySelector<HTMLInputElement>('[name="enabled"]')!.checked, days: selectedDays };
      await api(schedule ? `/schedules/${schedule.id}` : '/schedules', { method: schedule ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      toast('Schedule saved', 'success'); await refresh(); return true;
    },
  });
}
