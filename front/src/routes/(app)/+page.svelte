<script lang="ts">
	import { writable } from 'svelte/store';
	import ChrisChat from '$lib/components/chat/ChrisChat.svelte';
	import Chat from '$lib/components/chat/Chat.svelte';
	import Help from '$lib/components/layout/Help.svelte';

	// Persist UI preference; default to Chris UI
	const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('useChrisUI') : null;
	const useChrisUI = writable(stored !== 'false');

	useChrisUI.subscribe((val) => {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('useChrisUI', String(val));
		}
	});
</script>

<Help />

{#if $useChrisUI}
	<ChrisChat onSwitchUI={() => useChrisUI.set(false)} />
{:else}
	<Chat />
	<!-- Floating chip to return to Chris UI -->
	<button
		class="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2 rounded-full shadow-lg
		       bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700
		       text-sm font-medium text-gray-700 dark:text-gray-200
		       hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
		on:click={() => useChrisUI.set(true)}
	>
		<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-4 text-blue-500">
			<path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 0 1-.383-.218 25.18 25.18 0 0 1-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0 1 12 5.052 5.5 5.5 0 0 1 16.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 0 1-4.244 3.17 15.247 15.247 0 0 1-.383.219l-.022.012-.007.004-.003.001a.752.752 0 0 1-.704 0l-.003-.001Z" />
		</svg>
		Switch to Chris
	</button>
{/if}
