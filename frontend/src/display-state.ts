import type { Layout, RendererCapabilities, RendererFeature, RendererStatus } from './types.js';

export type LayoutDisplayState = {
  kind: 'applied' | 'pending' | 'focused' | 'inactive' | 'unknown';
  label: string;
  detail: string;
  action: string;
  tone: 'good' | 'warn' | 'neutral';
};

/** Database active is a startup preference, not proof that the saved revision is running. */
export function layoutDisplayState(layout: Pick<Layout, 'id' | 'current_revision' | 'active'> & Partial<Pick<Layout, 'revision'>>, renderer?: RendererStatus | null, expectedOutput?: { width: number; height: number }): LayoutDisplayState {
  if (!renderer || renderer.state === 'UNAVAILABLE' || renderer.active_layout_id === undefined) {
    return { kind: 'unknown', label: 'Display state unavailable', detail: `Revision ${layout.current_revision} is saved. Check the renderer before assuming it is displayed.`, action: 'Apply', tone: 'warn' };
  }
  if (renderer.active_layout_id !== layout.id) {
    return { kind: 'inactive', label: 'Saved layout', detail: `Revision ${layout.current_revision} is saved and is not the renderer's current layout.`, action: 'Apply', tone: 'neutral' };
  }
  if (renderer.active_revision == null) {
    return { kind: 'unknown', label: 'Applied revision unknown', detail: `Revision ${layout.current_revision} is saved; the renderer has not reported its revision.`, action: 'Reapply', tone: 'warn' };
  }
  if (renderer.active_revision > layout.current_revision) {
    return { kind: 'unknown', label: 'Saved view out of date', detail: `The renderer has revision ${renderer.active_revision}; refresh this page to load the latest saved layout.`, action: 'Reapply', tone: 'warn' };
  }
  if (renderer.active_revision < layout.current_revision) {
    return { kind: 'pending', label: 'Saved changes pending', detail: `Saved revision ${layout.current_revision}; renderer revision ${renderer.active_revision}.${renderer.focused ? ' Camera focus is active. Applying ends focus.' : ' Apply to update the display.'}`, action: 'Apply saved changes', tone: 'warn' };
  }
  if (renderer.active_revision_id && layout.revision?.id && renderer.active_revision_id !== layout.revision.id) {
    return { kind: 'pending', label: 'Saved changes pending', detail: 'The saved revision record differs from the one applied by the renderer, even though its revision number is the same. Apply to load the restored or imported version.', action: 'Apply saved changes', tone: 'warn' };
  }
  if (expectedOutput && renderer.output && (expectedOutput.width !== renderer.output.width || expectedOutput.height !== renderer.output.height)) {
    return { kind: 'pending', label: 'Saved display size pending', detail: `Saved render size ${expectedOutput.width} × ${expectedOutput.height}; renderer size ${renderer.output.width} × ${renderer.output.height}. Reapply to load the saved dimensions.${renderer.focused ? ' Applying ends focus.' : ''}`, action: 'Apply saved changes', tone: 'warn' };
  }
  if (renderer.focused) {
    return { kind: 'focused', label: 'Camera focus active', detail: `Revision ${renderer.active_revision} is the saved wall behind camera focus. Applying restores the wall and ends focus.`, action: 'Restore saved wall', tone: 'warn' };
  }
  return { kind: 'applied', label: `Applied revision ${renderer.active_revision}`, detail: 'The renderer has accepted this revision. Stream health reports playback separately.', action: 'Reapply', tone: 'good' };
}

export const rendererFeatures: Array<{ key: RendererFeature; label: string }> = [
  { key: 'labels', label: 'Camera labels' },
  { key: 'manual_crop', label: 'Manual crop' },
  { key: 'opacity', label: 'Tile opacity' },
  { key: 'z_order', label: 'Tile layering' },
  { key: 'audio', label: 'Audio playback' },
  { key: 'native_size', label: 'Native-size video' },
  { key: 'portrait', label: 'Display rotation' },
  { key: 'multiple_outputs', label: 'Multiple outputs' },
  { key: 'output_selection', label: 'Connector selection' },
  { key: 'refresh_rate', label: 'Refresh-rate control' },
  { key: 'prevent_blanking', label: 'Per-profile blanking control' },
  { key: 'background', label: 'Custom backgrounds' },
  { key: 'borders', label: 'Tile borders' },
];

/** Missing capability data stays unknown; backend presence alone does not imply support. */
export function featureSupport(capabilities: RendererCapabilities | undefined, key: RendererFeature): boolean | undefined {
  return capabilities?.feature_support?.[key];
}

export function featureDescription(capabilities: RendererCapabilities | undefined, key: RendererFeature): string {
  const support = featureSupport(capabilities, key);
  return support === true ? 'Supported' : support === false ? 'Not supported' : 'Not reported';
}
