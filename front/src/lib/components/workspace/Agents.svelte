<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';
	import { WEBUI_NAME, config, user, models } from '$lib/stores';
	import { getModels } from '$lib/apis';
	import { WEBUI_BASE_URL } from '$lib/constants';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
    import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
    import ArrowDownTray from '$lib/components/icons/ArrowDownTray.svelte';

	const i18n = getContext('i18n');

	let loaded = false;
	let agents = [];
	let filteredAgents = [];
	let searchValue = '';

    let showAddModal = false;
    let addUrl = '';
    let addImageUrl = '';
    let addSubmitting = false;

	$: if (agents) {
		filteredAgents = agents.filter(
			(a) => searchValue === '' || a.name.toLowerCase().includes(searchValue.toLowerCase())
		);
	}

    const fetchAgents = async () => {
        try {
            const res = await fetch(`${WEBUI_BASE_URL}/api/v1/registry/`, {
                headers: { 'Authorization': `Bearer ${localStorage.token}` }
            });
            if (res.ok) {
                agents = await res.json();
            } else {
                toast.error('Failed to fetch agents');
            }
        } catch (e) {
            toast.error('Failed to fetch agents');
        }
    };

    const addAgent = async () => {
        if (!addUrl || addSubmitting) return;
        addSubmitting = true;
        try {
            const res = await fetch(`${WEBUI_BASE_URL}/api/v1/agents/register-by-url`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    agent_url: addUrl,
                    profile_image_url: addImageUrl || undefined
                })
            });

            if (res.ok) {
                toast.success('Agent added successfully');
                showAddModal = false;
                addUrl = '';
                addImageUrl = '';
                models.set(await getModels(localStorage.token));
                await fetchAgents();
            } else {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || 'Failed to add agent');
            }
        } catch (e) {
            toast.error('Failed to add agent');
        } finally {
            addSubmitting = false;
        }
    };

    const deleteAgent = async (id) => {
        try {
            const res = await fetch(`${WEBUI_BASE_URL}/api/v1/registry/${id}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${localStorage.token}` }
            });
            if (res.ok) {
                toast.success('Agent deleted');
                await fetchAgents();
            } else {
                toast.error('Failed to delete agent');
            }
        } catch (e) {
            toast.error('Failed to delete agent');
        }
    };

    const installAgent = async (agent) => {
        try {
            const res = await fetch(`${WEBUI_BASE_URL}/api/v1/agents/register-by-url`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    agent_url: agent.url,
                    profile_image_url: agent.image_url
                })
            });

            if (res.ok) {
                toast.success('Agent installed successfully');
                models.set(await getModels(localStorage.token));
            } else {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || 'Failed to install agent');
            }
        } catch (e) {
            toast.error('Failed to install agent');
        }
    };

	onMount(async () => {
		await fetchAgents();
		loaded = true;
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Agents')} | {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
    <!-- Add Agent Modal -->
    {#if showAddModal}
        <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-6 w-full max-w-md shadow-xl">
                <h2 class="text-xl font-semibold mb-4">{$i18n.t('Add Agent')}</h2>

                <div class="mb-4">
                    <label class="block text-sm font-medium mb-1">{$i18n.t('Agent URL')}</label>
                    <input
                        type="text"
                        bind:value={addUrl}
                        placeholder="http://localhost:8002"
                        class="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                    />
                    <p class="text-xs text-gray-500 mt-1">{$i18n.t('URL must host a .well-known/agent.json file')}</p>
                </div>

                <div class="mb-4">
                    <label class="block text-sm font-medium mb-1">{$i18n.t('Agent Image URL (Optional)')}</label>
                    <input
                        type="text"
                        bind:value={addImageUrl}
                        placeholder="https://example.com/image.png"
                        class="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                    />
                </div>

                <div class="flex justify-end gap-2">
                    <button
                        class="px-4 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
                        on:click={() => { showAddModal = false; addUrl = ''; addImageUrl = ''; }}
                    >
                        {$i18n.t('Cancel')}
                    </button>
                    <button
                        class="px-4 py-2 rounded-lg bg-black dark:bg-white text-white dark:text-black font-medium disabled:opacity-50"
                        disabled={!addUrl || addSubmitting}
                        on:click={addAgent}
                    >
                        {addSubmitting ? $i18n.t('Adding...') : $i18n.t('Add')}
                    </button>
                </div>
            </div>
        </div>
    {/if}

	<div class="flex flex-col gap-1 my-1.5">
		<div class="flex justify-between items-center">
			<div class="flex items-center md:self-center text-xl font-medium px-0.5">
				{$i18n.t('Agents')}
				<div class="flex self-center w-[1px] h-6 mx-2.5 bg-gray-50 dark:bg-gray-850" />
				<span class="text-lg font-medium text-gray-500 dark:text-gray-300"
					>{filteredAgents.length}</span
				>
			</div>
		</div>

		<div class=" flex flex-1 items-center w-full space-x-2">
			<div class="flex flex-1 items-center">
				<div class=" self-center ml-1 mr-3">
					<Search className="size-3.5" />
				</div>
				<input
					class=" w-full text-sm py-1 rounded-r-xl outline-hidden bg-transparent"
					bind:value={searchValue}
					placeholder={$i18n.t('Search Agents')}
				/>
			</div>

			<div class="flex items-center gap-1">
				{#if $user?.role === 'admin'}
					<a
						href="/workspace/agents/deploy"
						class="px-3 py-2 rounded-xl bg-black dark:bg-white text-white dark:text-black hover:opacity-80 transition font-medium text-xs"
					>
						{$i18n.t('Deploy new agent')}
					</a>
				{/if}
				<button
					class=" px-2 py-2 rounded-xl hover:bg-gray-700/10 dark:hover:bg-gray-100/10 dark:text-gray-300 dark:hover:text-white transition font-medium text-sm flex items-center space-x-1"
					on:click={() => showAddModal = true}
				>
					<Plus className="size-3.5" />
				</button>
			</div>
		</div>
	</div>

	<div class=" my-2 mb-5 gap-2 grid lg:grid-cols-2 xl:grid-cols-3" id="agent-list">
		{#each filteredAgents as agent}
			<div
				class=" flex flex-col w-full px-3 py-2 dark:bg-white/5 bg-black/5 rounded-xl transition border border-transparent hover:border-gray-200 dark:hover:border-gray-700"
			>
				<div class="flex gap-4 mt-0.5 mb-0.5">
					<div class=" w-[44px] shrink-0">
						<div class=" rounded-full object-cover">
							<img
								src={agent.image_url ?? '/static/favicon.png'}
								alt="agent profile"
								class=" rounded-full w-full h-auto object-cover"
                                onError={(e) => e.target.src = '/static/favicon.png'}
							/>
						</div>
					</div>

					<div class=" flex flex-col flex-1 min-w-0">
                        <div class="flex justify-between items-start">
                            <div class="font-semibold line-clamp-1 break-all" title={agent.name}>{agent.name}</div>
                            
                            <!-- Actions -->
                            <div class="flex items-center gap-1">
                                <Tooltip content={$i18n.t('Install')}>
                                    <button 
                                        class="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-600 dark:text-gray-300"
                                        on:click={() => installAgent(agent)}
                                    >
                                        <ArrowDownTray className="size-4" />
                                    </button>
                                </Tooltip>
                                
                                {#if $user?.role === 'admin' || agent.user_id === $user?.id}
                                    <Tooltip content={$i18n.t('Delete')}>
                                        <button 
                                            class="p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400 transition"
                                            on:click={() => deleteAgent(agent.id)}
                                        >
                                            <GarbageBin className="size-4" />
                                        </button>
                                    </Tooltip>
                                {/if}
                            </div>
                        </div>

                        <div class="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 mt-1" title={agent.description}>
                            {agent.description || $i18n.t('No description')}
                        </div>
                        
                        <div class="mt-2 flex flex-wrap gap-1">
                            {#if agent.foundational_model}
                                <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                                    {agent.foundational_model}
                                </span>
                            {/if}
                            {#if agent.tools?.capabilities}
                                {#each Object.keys(agent.tools.capabilities) as cap}
                                    <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                                        {cap}
                                    </span>
                                {/each}
                            {/if}
                        </div>
					</div>
				</div>
                
                <div class="mt-2 pt-2 border-t border-gray-100 dark:border-gray-800 flex justify-between items-center text-xs text-gray-500">
                     <div class="truncate max-w-[200px]" title={agent.url}>{agent.url}</div>
                </div>
			</div>
		{/each}
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner />
	</div>
{/if}
