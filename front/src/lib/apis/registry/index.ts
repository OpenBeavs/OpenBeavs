import { WEBUI_BASE_URL } from '$lib/constants';

export interface RegistryAgent {
	id: string;
	user_id: string;
	url: string;
	name: string;
	description: string | null;
	image_url: string | null;
	foundational_model: string | null;
	tools: { capabilities?: Record<string, unknown>; skills?: unknown[] } | null;
	access_control: Record<string, unknown> | null;
	card_url: string | null;
	is_featured: boolean;
	created_at: number;
	updated_at: number;
}

export interface UpdateRegistryAgentForm {
	access_control?: Record<string, unknown> | null;
	name?: string;
	description?: string;
	image_url?: string;
	is_featured?: boolean;
}

export const getRegistryAgents = async (token: string): Promise<RegistryAgent[]> => {
	const res = await fetch(`${WEBUI_BASE_URL}/api/v1/registry/`, {
		headers: { Authorization: `Bearer ${token}` }
	});
	if (!res.ok) throw new Error('Failed to fetch registry agents');
	return res.json();
};

export const getFeaturedAgents = async (token: string): Promise<RegistryAgent[]> => {
	const res = await fetch(`${WEBUI_BASE_URL}/api/v1/registry/featured`, {
		headers: { Authorization: `Bearer ${token}` }
	});
	if (!res.ok) throw new Error('Failed to fetch featured agents');
	return res.json();
};

export const submitRegistryAgent = async (
	token: string,
	url: string,
	imageUrl?: string
): Promise<RegistryAgent> => {
	const res = await fetch(`${WEBUI_BASE_URL}/api/v1/registry/`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({ url, image_url: imageUrl ?? null, access_control: {} })
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({}));
		throw new Error((err as { detail?: string }).detail ?? 'Failed to submit agent');
	}
	return res.json();
};

export const updateRegistryAgent = async (
	token: string,
	id: string,
	data: UpdateRegistryAgentForm
): Promise<RegistryAgent> => {
	const res = await fetch(`${WEBUI_BASE_URL}/api/v1/registry/${id}`, {
		method: 'PUT',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({}));
		throw new Error((err as { detail?: string }).detail ?? 'Failed to update agent');
	}
	return res.json();
};

export const deleteRegistryAgent = async (token: string, id: string): Promise<void> => {
	const res = await fetch(`${WEBUI_BASE_URL}/api/v1/registry/${id}`, {
		method: 'DELETE',
		headers: { Authorization: `Bearer ${token}` }
	});
	if (!res.ok) throw new Error('Failed to delete agent');
};
