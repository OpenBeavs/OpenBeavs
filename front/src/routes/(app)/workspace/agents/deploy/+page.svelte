<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { WEBUI_NAME, user, models } from '$lib/stores';
	import { getModels } from '$lib/apis';
	import { deployAgent, type DeployAgentForm } from '$lib/apis/agents';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';

	const i18n = getContext('i18n') as any;

	const PROVIDER_DEFAULTS: Record<string, string> = {
		anthropic: 'claude-sonnet-4-6',
		openai: 'gpt-4o',
		gemini: 'gemini-2.0-flash'
	};

	let loaded = false;
	let submitting = false;

	let name = '';
	let description = '';
	let systemPrompt = '';
	let provider: 'anthropic' | 'openai' | 'gemini' = 'anthropic';
	let model = PROVIDER_DEFAULTS['anthropic'];
	let profileImageUrl = '';
	let publishToRegistry = true;
	let deployToCloudRun = false;

	let modelTouched = false;

	$: if (!modelTouched) {
		model = PROVIDER_DEFAULTS[provider];
	}

	$: canSubmit =
		name.trim().length > 0 && description.trim().length > 0 && systemPrompt.trim().length > 0;

	const onSubmit = async () => {
		if (!canSubmit || submitting) return;
		submitting = true;

		const form: DeployAgentForm = {
			name: name.trim(),
			description: description.trim(),
			system_prompt: systemPrompt,
			provider,
			model: model || undefined,
			profile_image_url: profileImageUrl.trim() || undefined,
			publish_to_registry: publishToRegistry,
			deploy_to_cloud_run: deployToCloudRun
		};

		try {
			const agent = await deployAgent(localStorage.token, form);
			toast.success($i18n.t('Agent deployed'));
			models.set(await getModels(localStorage.token));
			await goto('/workspace/agents');
		} catch (err: any) {
			toast.error(err?.detail || $i18n.t('Failed to deploy agent'));
		} finally {
			submitting = false;
		}
	};

	onMount(() => {
		if ($user?.role !== 'admin') {
			goto('/');
			return;
		}
		loaded = true;
	});
</script>

<svelte:head>
	<title>{$i18n.t('Deploy Agent')} | {$WEBUI_NAME}</title>
</svelte:head>

{#if loaded}
	<div class="mx-auto max-w-3xl w-full p-1">
		<div class="flex flex-col gap-1 my-1.5">
			<div class="text-xl font-medium px-0.5">{$i18n.t('Deploy Agent')}</div>
			<div class="text-xs text-gray-500 px-0.5">
				{$i18n.t(
					'Create a new A2A-compatible agent hosted by this hub. Write a system prompt and the agent becomes chattable immediately.'
				)}
			</div>
		</div>

		<form
			class="flex flex-col gap-4 mt-4"
			on:submit|preventDefault={onSubmit}
		>
			<div>
				<label class="block text-sm font-medium mb-1">{$i18n.t('Name')}</label>
				<input
					type="text"
					bind:value={name}
					placeholder="Support Bot"
					class="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
					required
				/>
			</div>

			<div>
				<label class="block text-sm font-medium mb-1">{$i18n.t('Description')}</label>
				<input
					type="text"
					bind:value={description}
					placeholder={$i18n.t('What does this agent do?')}
					class="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
					required
				/>
			</div>

			<div>
				<label class="block text-sm font-medium mb-1">{$i18n.t('System Prompt')}</label>
				<Textarea
					bind:value={systemPrompt}
					placeholder={$i18n.t(
						'Describe the agent\u2019s role and behavior. e.g. "You answer Oregon State University questions in one short paragraph."'
					)}
					rows={6}
				/>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-sm font-medium mb-1">{$i18n.t('Provider')}</label>
					<select
						bind:value={provider}
						class="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
					>
						<option value="anthropic">Anthropic</option>
						<option value="openai">OpenAI</option>
						<option value="gemini">Gemini</option>
					</select>
				</div>
				<div>
					<label class="block text-sm font-medium mb-1">{$i18n.t('Model')}</label>
					<input
						type="text"
						bind:value={model}
						on:input={() => (modelTouched = true)}
						placeholder={PROVIDER_DEFAULTS[provider]}
						class="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
					/>
				</div>
			</div>

			<div>
				<label class="block text-sm font-medium mb-1">
					{$i18n.t('Profile Image URL')} <span class="text-gray-500">({$i18n.t('optional')})</span>
				</label>
				<input
					type="text"
					bind:value={profileImageUrl}
					placeholder="https://example.com/avatar.png"
					class="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
				/>
			</div>

			<label class="flex items-center gap-2 mt-1">
				<Checkbox
					state={publishToRegistry ? 'checked' : 'unchecked'}
					on:change={(e) => (publishToRegistry = e.detail === 'checked')}
				/>
				<span class="text-sm">{$i18n.t('Publish to marketplace')}</span>
			</label>

			<label class="flex items-start gap-2">
				<Checkbox
					state={deployToCloudRun ? 'checked' : 'unchecked'}
					on:change={(e) => (deployToCloudRun = e.detail === 'checked')}
				/>
				<span class="text-sm flex flex-col">
					<span>{$i18n.t('Deploy to dedicated Cloud Run service (recommended for production)')}</span>
					<span class="text-xs text-gray-500">
						{$i18n.t(
							'Provisions a per-agent Cloud Run service with its own URL and secrets. Requires gcloud credentials on the hub host. Leave unchecked to host the agent inside this hub instance.'
						)}
					</span>
				</span>
			</label>

			<div class="flex justify-end gap-2 mt-2">
				<button
					type="button"
					class="px-4 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
					on:click={() => goto('/workspace/agents')}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					type="submit"
					class="px-4 py-2 rounded-lg bg-black dark:bg-white text-white dark:text-black font-medium disabled:opacity-50"
					disabled={!canSubmit || submitting}
				>
					{submitting ? $i18n.t('Deploying...') : $i18n.t('Deploy')}
				</button>
			</div>
		</form>
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner />
	</div>
{/if}
