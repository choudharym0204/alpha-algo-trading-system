"use client";

import { useAuth } from "@/context/auth-context";
import { API_BASE_URL, WS_URL } from "@/lib/env";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";

export default function SettingsPage() {
  const { user, permissions, logout } = useAuth();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-white">Settings</h1>

      <Card>
        <CardHeader title="Session" />
        <CardContent>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted">Subject</dt>
              <dd className="text-white">{user?.subject ?? "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">API base URL</dt>
              <dd className="text-white">{API_BASE_URL}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">WebSocket URL</dt>
              <dd className="text-white">{WS_URL}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader title="Permissions" />
        <CardContent>
          <Table>
            <THead>
              <Th>Permission</Th>
              <Th>Status</Th>
            </THead>
            <TBody>
              {permissions.length === 0 ? (
                <Tr>
                  <Td className="text-muted">No permissions granted.</Td>
                  <Td />
                </Tr>
              ) : (
                permissions.map((permission) => (
                  <Tr key={permission}>
                    <Td>{permission}</Td>
                    <Td>
                      <Badge variant="success">Granted</Badge>
                    </Td>
                  </Tr>
                ))
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader title="Sign out" />
        <CardContent>
          <p className="mb-3 text-sm text-muted">
            Ends the current session. Tokens are held in memory only and are cleared on sign-out.
          </p>
          <button
            onClick={logout}
            className="rounded-md bg-sell px-3 py-2 text-sm font-medium text-white hover:bg-red-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sell"
          >
            Sign out
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
