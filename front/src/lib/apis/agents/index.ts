import { WEBUI_API_BASE_URL } from '$lib/constants';

export type DeployAgentForm = {
	name: string;
	description: string;
	system_prompt: string;
	provider?: 'anthropic' | 'openai' | 'gemini';
	model?: string;
	profile_image_url?: string;
	publish_to_registry?: boolean;
	deploy_to_cloud_run?: boolean;
};

export const deployAgent = async (token: string, form: DeployAgentForm) => {
	let error: unknown = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/agents/deploy`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(form)
	})
		.then(async (r) => {
			if (!r.ok) throw await r.json();
			return r.json();
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) throw error;
	return res;
};
