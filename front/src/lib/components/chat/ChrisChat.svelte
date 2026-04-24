<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import {
		sendChrisMessage,
		getChrisSuggestions,
		installAgentByUrl,
		type ChrisMessageResponse,
		type SuggestionItem,
		type HistoryMessage
	} from '$lib/apis/chris';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Sparkles from '$lib/components/icons/Sparkles.svelte';
	import ArrowUpCircle from '$lib/components/icons/ArrowUpCircle.svelte';

	// ── Types ─────────────────────────────────────────────────────────────────

	type InstalledAgent = {
		id: string;
		name: string;
		description: string | null;
		profile_image_url: string | null;
	};

	type ChatMessage = {
		id: string;
		role: 'user' | 'assistant';
		content: string;
		routed_to: string | null;
		agent_name: string | null;
	};

	// ── State ──────────────────────────────────────────────────────────────────

	let messages: ChatMessage[] = [];
	let input = '';
	let loading = false;
	let messagesEl: HTMLElement;

	// #140: installed agents for quick-launch panel
	let installedAgents: InstalledAgent[] = [];
	let agentsLoading = true;

	// #139: marketplace suggestion chips shown after a non-routed reply
	let suggestions: SuggestionItem[] = [];
	let installingId: string | null = null;

	// Targeted agent — set when user clicks a quick-launch chip (#140)
	let targetedAgent: InstalledAgent | null = null;

	// ── Lifecycle ──────────────────────────────────────────────────────────────

	onMount(async () => {
		await fetchInstalledAgents();
	});

	// ── Helpers ────────────────────────────────────────────────────────────────

	async function fetchInstalledAgents() {
		agentsLoading = true;
		try {
			const res = await fetch(`${WEBUI_API_BASE_URL}/agents/`, {
				headers: { Authorization: `Bearer ${localStorage.token}` }
			});
			if (res.ok) {
				installedAgents = await res.json();
			}
		} catch {
			// silently ignore — panel just stays empty
		} finally {
			agentsLoading = false;
		}
	}

	function scrollToBottom() {
		tick().then(() => {
			if (messagesEl) {
				messagesEl.scrollTop = messagesEl.scrollHeight;
			}
		});
	}

	function buildHistory(): HistoryMessage[] {
		return messages.map((m) => ({ role: m.role, content: m.content }));
	}

	function uniqueId(): string {
		return Math.random().toString(36).slice(2);
	}

	// ── Send message ───────────────────────────────────────────────────────────

	async function send() {
		const text = input.trim();
		if (!text || loading) return;

		suggestions = [];

		// Prepend targeted agent name to message if user picked a specific agent
		const effectiveMessage = targetedAgent ? `[To ${targetedAgent.name}] ${text}` : text;

		messages = [
			...messages,
			{ id: uniqueId(), role: 'user', content: text, routed_to: null, agent_name: null }
		];
		input = '';
		loading = true;
		scrollToBottom();

		try {
			const history = buildHistory().slice(0, -1); // exclude the message we just added
			const result: ChrisMessageResponse | null = await sendChrisMessage(
				localStorage.token,
				{ message: effectiveMessage, history }
			);

			if (result) {
				messages = [
					...messages,
					{
						id: uniqueId(),
						role: 'assistant',
						content: result.response,
						routed_to: result.routed_to,
						agent_name: result.agent_name
					}
				];

				// #139: fetch suggestions only when Chris answered directly (no agent routed)
				if (!result.routed_to) {
					suggestions = await getChrisSuggestions(localStorage.token, text, 3);
				}
			}
		} catch (e) {
			messages = [
				...messages,
				{
					id: uniqueId(),
					role: 'assistant',
					content: 'Chris is temporarily unavailable. Please try again shortly.',
					routed_to: null,
					agent_name: null
				}
			];
		} finally {
			loading = false;
			targetedAgent = null;
			scrollToBottom();
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	// #139: install a suggested agent then refresh the installed list
	async function installSuggestion(item: SuggestionItem) {
		installingId = item.id;
		try {
			const ok = await installAgentByUrl(localStorage.token, item.url);
			if (ok) {
				suggestions = suggestions.filter((s) => s.id !== item.id);
				await fetchInstalledAgents();
			}
		} finally {
			installingId = null;
		}
	}

	// #140: select or deselect a quick-launch agent
	function toggleTargetAgent(agent: InstalledAgent) {
		targetedAgent = targetedAgent?.id === agent.id ? null : agent;
	}
</script>

<!-- ── Layout ──────────────────────────────────────────────────────────────── -->
<div class="h-screen max-h-[100dvh] w-full flex flex-col overflow-hidden">
<div class="flex flex-col flex-1 overflow-hidden w-full max-w-3xl mx-auto px-4 pb-4 pt-8">

	<!-- Header -->
	<div class="flex items-center gap-2 mb-6">
		<Sparkles className="w-6 h-6 text-blue-500" />
		<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Chris</h1>
		<span class="text-sm text-gray-500 dark:text-gray-400">OpenBeavs AI Hub</span>
	</div>

	<!-- Message thread -->
	<div
		bind:this={messagesEl}
		class="flex-1 overflow-y-auto space-y-4 mb-4 pr-1"
	>
		{#if messages.length === 0}
			<div class="flex flex-col items-center justify-center h-full gap-3 text-center py-16">
				<Sparkles className="w-10 h-10 text-blue-400" />
				<p class="text-gray-600 dark:text-gray-400 text-sm max-w-xs">
					Ask Chris anything — he'll route your question to the right agent or answer directly.
				</p>
			</div>
		{/if}

		{#each messages as msg (msg.id)}
			<div class="flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
				<div class="flex flex-col gap-1 max-w-[80%]">

					<!-- #138: routing indicator for assistant messages -->
					{#if msg.role === 'assistant' && msg.agent_name}
						<div class="flex items-center gap-1.5 px-1">
							<span
								class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium
								       bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
							>
								<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round"
										d="M13 10V3L4 14h7v7l9-11h-7z" />
								</svg>
								Routed to {msg.agent_name}
							</span>
						</div>
					{/if}

					<!-- Bubble -->
					<div
						class="rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words
						       {msg.role === 'user'
							       ? 'bg-blue-600 text-white rounded-tr-sm'
							       : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-tl-sm'}"
					>
						{msg.content}
					</div>
				</div>
			</div>
		{/each}

		<!-- Typing indicator -->
		{#if loading}
			<div class="flex justify-start">
				<div class="bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
					<Spinner className="size-4" />
				</div>
			</div>
		{/if}

		<!-- #139: marketplace suggestion chips -->
		{#if suggestions.length > 0 && !loading}
			<div class="flex flex-col gap-2 pl-1">
				<p class="text-xs text-gray-500 dark:text-gray-400">
					Agents that might help:
				</p>
				<div class="flex flex-wrap gap-2">
					{#each suggestions as item (item.id)}
						<button
							class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
							       border border-gray-300 dark:border-gray-600
							       bg-white dark:bg-gray-800
							       text-gray-700 dark:text-gray-300
							       hover:bg-gray-50 dark:hover:bg-gray-700
							       disabled:opacity-50 transition-colors"
							disabled={installingId === item.id}
							on:click={() => installSuggestion(item)}
							title={item.description ?? ''}
						>
							{#if installingId === item.id}
								<Spinner className="size-3" />
							{:else}
								<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
								</svg>
							{/if}
							{item.name}
						</button>
					{/each}
				</div>
			</div>
		{/if}
	</div>

	<!-- #140: installed agent quick-launch panel -->
	{#if !agentsLoading && installedAgents.length > 0}
		<div class="flex flex-wrap gap-2 mb-3">
			{#each installedAgents as agent (agent.id)}
				<button
					class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium
					       border transition-colors
					       {targetedAgent?.id === agent.id
						       ? 'bg-blue-600 text-white border-blue-600'
						       : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'}"
					on:click={() => toggleTargetAgent(agent)}
					title={agent.description ?? agent.name}
				>
					{#if agent.profile_image_url}
						<img src={agent.profile_image_url} alt="" class="w-3.5 h-3.5 rounded-full object-cover" />
					{:else}
						<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round"
								d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 1-6.23-.693L5 14.5m14.8.8 1.402 1.402c1 1 .28 2.716-1.103 2.716H4.9c-1.383 0-2.103-1.716-1.103-2.716L5 14.5" />
						</svg>
					{/if}
					{agent.name}
				</button>
			{/each}
		</div>
	{/if}

	<!-- Targeted agent banner -->
	{#if targetedAgent}
		<div class="flex items-center justify-between mb-2 px-3 py-1.5 rounded-lg bg-blue-50 dark:bg-blue-900/20 text-xs text-blue-700 dark:text-blue-300">
			<span>Sending directly to <strong>{targetedAgent.name}</strong></span>
			<button
				class="hover:text-blue-900 dark:hover:text-blue-100 font-medium"
				on:click={() => (targetedAgent = null)}
			>
				✕
			</button>
		</div>
	{/if}

	<!-- Input row -->
	<div class="flex items-end gap-2 rounded-2xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-3 shadow-sm">
		<textarea
			class="flex-1 resize-none bg-transparent text-sm text-gray-900 dark:text-gray-100 outline-none placeholder-gray-400 dark:placeholder-gray-500 max-h-40"
			placeholder="Message Chris..."
			rows="1"
			bind:value={input}
			on:keydown={handleKeydown}
			on:input={(e) => {
				const t = e.currentTarget;
				t.style.height = 'auto';
				t.style.height = t.scrollHeight + 'px';
			}}
		/>
		<button
			class="flex-shrink-0 text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300
			       disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
			disabled={!input.trim() || loading}
			on:click={send}
			aria-label="Send"
		>
			<ArrowUpCircle className="w-7 h-7" />
		</button>
	</div>
</div>
</div>
