import React from 'react';
import type { MappingSessionState } from './mappingSessionPersistence';
import { formatMappingSessionStatusLine } from './mappingSessionPersistence';

type Props = {
  session: MappingSessionState;
  onResume: () => void;
  onStartNew: () => void;
  onOpenExplorer: () => void;
};

export function MappingSessionResumeModal({ session, onResume, onStartNew, onOpenExplorer }: Props) {
  const summary = formatMappingSessionStatusLine(session);
  return (
    <div className="mappingSessionModalBackdrop" role="presentation">
      <div className="mappingSessionModal" role="dialog" aria-labelledby="mapping-session-resume-title">
        <h3 id="mapping-session-resume-title">Resume Mapping Session?</h3>
        <p className="mappingSessionModalSummary">{summary}</p>
        <p className="mappingSessionModalHint">
          Restore layer, parent, research window, and candidate position from your last mapping pass.
        </p>
        <div className="mappingSessionModalActions">
          <button type="button" className="primary" onClick={onResume}>Resume</button>
          <button type="button" onClick={onStartNew}>Start New Session</button>
          <button type="button" className="secondary" onClick={onOpenExplorer}>Open Explorer</button>
        </div>
      </div>
    </div>
  );
}
