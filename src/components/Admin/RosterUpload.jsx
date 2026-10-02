import React, { useState, useRef } from 'react';
import { Upload, FileSpreadsheet, Copy, Download } from 'lucide-react';
import { SectionHeader, Card, CardBody, CardHead, Callout, DataTable, Pill } from '../UI';
import { rosterApi, ROSTER_COLUMNS } from '../../lib/roster';
import { errorMessage } from '../../lib/enrollment';

const sampleCsv = `${ROSTER_COLUMNS.join(',')},date_of_birth
FE24B001,Amina,Mbeki,amina.mbeki@fet.edu,200,CS,2005-03-14
FE24B002,Thabo,Ndlovu,thabo.ndlovu@fet.edu,200,CS,2004-11-02
`;

const RosterUpload = () => {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const pick = (e) => {
    setError('');
    setResult(null);
    const f = e.target.files?.[0];
    setFile(f || null);
  };

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      setResult(await rosterApi.upload(file));
    } catch (err) {
      setError(errorMessage(err, 'Upload failed.'));
    } finally {
      setBusy(false);
    }
  };

  const copyPasswords = async () => {
    const text = (result?.created || [])
      .map((c) => `${c.email}\t${c.full_name}\t${c.temp_password}`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError('Could not copy — select the table and copy manually.');
    }
  };

  const downloadTemplate = () => {
    const blob = new Blob([sampleCsv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'roster-template.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      <SectionHeader
        area="hub"
        icon={Upload}
        title="Roster upload"
        subtitle="The only way a student account comes into existence. Public sign-up is disabled, so nobody can invent a matricule."
        actions={(
          <button type="button" onClick={downloadTemplate} className="fet-btn-secondary">
            <Download size={14} /> CSV template
          </button>
        )}
      />

      <Callout tone="in">
        Required columns: <b className="num">{ROSTER_COLUMNS.join(', ')}</b>.
        Optional: <b className="num">date_of_birth</b> (YYYY-MM-DD).
        Re-uploading a row that already exists updates the profile and leaves the
        existing password alone, so this is safe to run again.
      </Callout>

      {error ? <Callout tone="bad">{error}</Callout> : null}

      <Card accent="hub">
        <CardHead title="Upload a roster" square="hub" />
        <CardBody>
          <div className="space-y-3">
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={pick}
              className="fet-input"
            />
            <div className="flex items-center gap-3 flex-wrap">
              <button
                type="button"
                onClick={upload}
                disabled={!file || busy}
                className="fet-btn-primary"
              >
                <Upload size={14} /> {busy ? 'Uploading...' : 'Upload roster'}
              </button>
              {file ? (
                <span className="text-[12.5px] text-text-secondary flex items-center gap-1.5">
                  <FileSpreadsheet size={14} /> {file.name}
                </span>
              ) : null}
            </div>
          </div>
        </CardBody>
      </Card>

      {result ? (
        <>
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Accounts created', value: result.created_count, tone: 'ok' },
              { label: 'Profiles updated', value: result.updated_count, tone: 'mute' },
              { label: 'Rows rejected', value: result.error_count, tone: result.error_count ? 'bad' : 'mute' },
            ].map((s) => (
              <Card key={s.label} accent="hub" className="h-full">
                <div className="ui-stat">
                  <div className="min-w-0">
                    <p className="ui-eyebrow">{s.label}</p>
                    <div className="ui-stat-value">{s.value ?? 0}</div>
                  </div>
                </div>
              </Card>
            ))}
          </div>

          {result.created?.length ? (
            <Card accent="hub">
              <CardHead title="New accounts — copy these now" square="hub">
                <button type="button" onClick={copyPasswords} className="fet-btn-secondary text-[12px]">
                  <Copy size={13} /> {copied ? 'Copied' : 'Copy all'}
                </button>
              </CardHead>
              <CardBody>
                <Callout tone="warn" className="mb-3">
                  These temporary passwords are shown once and cannot be retrieved again.
                  Students must change them at first sign-in.
                </Callout>
                <DataTable
                  rows={result.created}
                  columns={[
                    { key: 'full_name', label: 'Student' },
                    { key: 'email', label: 'Email' },
                    { key: 'matricule', label: 'Matricule', width: '130px' },
                    {
                      key: 'temp_password',
                      label: 'Temporary password',
                      width: '180px',
                      render: (r) => <b className="num text-[13px]">{r.temp_password}</b>,
                    },
                  ]}
                />
              </CardBody>
            </Card>
          ) : null}

          {result.errors?.length ? (
            <Card accent="hub">
              <CardHead title="Rejected rows" square="hub">
                <Pill tone="bad">{result.errors.length}</Pill>
              </CardHead>
              <CardBody>
                <ul className="space-y-1.5">
                  {result.errors.map((e, i) => (
                    <li key={i} className="text-[12.5px] text-text-secondary">
                      {e.line ? <b className="num">Line {e.line}:</b> : null}{' '}
                      {e.matricule ? <span className="num">{e.matricule}</span> : null}{' '}
                      {e.error}
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          ) : null}
        </>
      ) : null}
    </div>
  );
};

export default RosterUpload;
