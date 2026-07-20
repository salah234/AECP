"use client";

/**
 * Decision log view: read-only history of why things were built a
 * certain way, backed by GET /api/v1/decisions via lib/api-client.ts.
 * StateService has no list-by-tenant RPC yet (only single-entry
 * RecordDecision and exact-id GetInterfaceContract), so the decision
 * list below shows an honest "not available yet" notice; the contract
 * lookup form does work end to end, since GetInterfaceContract is real.
 */

import { useState } from "react";

import { AsyncSection } from "@/components/AsyncSection";
import { AuthGuard } from "@/components/AuthGuard";
import { ApiError, getInterfaceContract, listDecisions, type InterfaceContract } from "@/lib/api-client";
import { useAsync } from "@/lib/useAsync";

function ContractLookup() {
  const [contractId, setContractId] = useState("");
  const [result, setResult] = useState<InterfaceContract | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await getInterfaceContract(contractId));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to fetch contract");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <form className="inline-form" onSubmit={handleSubmit}>
        <label>
          Contract ID
          <input value={contractId} onChange={(e) => setContractId(e.target.value)} required />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Looking up…" : "Look up"}
        </button>
      </form>
      {error && <p className="error-text">{error}</p>}
      {result && (
        <table style={{ marginTop: 12 }}>
          <tbody>
            <tr>
              <th>Name</th>
              <td>{result.name}</td>
            </tr>
            <tr>
              <th>Version</th>
              <td>{result.version}</td>
            </tr>
            <tr>
              <th>Frozen</th>
              <td>{result.frozen ? "yes" : "no"}</td>
            </tr>
            <tr>
              <th>Schema</th>
              <td>
                <code>{result.schema}</code>
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function DecisionsPage() {
  const state = useAsync(listDecisions, []);

  return (
    <AuthGuard>
      {() => (
        <>
          <h1>Decisions</h1>
          <p className="subtitle">Why something was built a certain way, not just what.</p>

          <h2>Interface contract lookup</h2>
          <ContractLookup />

          <h2>Decision log</h2>
          <AsyncSection state={state}>
            {(entries) =>
              entries.length === 0 ? (
                <p className="muted">No decisions recorded.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Summary</th>
                      <th>Rationale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry) => (
                      <tr key={entry.entryId}>
                        <td>{entry.taskId}</td>
                        <td>{entry.summary}</td>
                        <td>{entry.rationale}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            }
          </AsyncSection>
        </>
      )}
    </AuthGuard>
  );
}
