import torch
from torch import nn
from torch.nn import Module

from beartype import beartype
from beartype.typing import Optional, Tuple, Union

from einops import rearrange

# helper functions

def exists(val):
    return val is not None

def is_all_unique(arr):
    return len(set(arr)) == len(arr)

def filter_tuple_indices(tup, indices):
    return tuple(tup[i] for i in indices)

# embedding wrapper class

class EmbeddingWrapper(Module):
    @beartype
    def __init__(
        self,
        embed: nn.Embedding,
        num_concepts = 1
    ):
        super().__init__()
        self.embed = embed
        num_embeds, dim = embed.weight.shape

        self.num_embeds = num_embeds
        self.num_concepts = num_concepts
        self.concepts = nn.Parameter(torch.zeros(num_concepts, dim))
        nn.init.normal_(self.concepts, std = 0.02)

        self.concept_embed_ids = tuple(range(num_embeds, num_embeds + num_concepts))

    def parameters(self):
        return [self.concepts]

    def forward(
        self,
        x,
        concept_id: Optional[Union[int, Tuple[int, ...]]] = None
    ):
        concept_masks = tuple(concept_id == x for concept_id in self.concept_embed_ids)

        if exists(concept_id):
            if not isinstance(concept_id, tuple):
                concept_id = (concept_id,)

            assert is_all_unique(concept_id), 'concept ids must be all unique'
            assert all([cid < self.num_concepts for cid in concept_id])

            has_concept = tuple(concept_mask.any(dim = -1).all() for concept_mask in concept_masks)

            assert all(filter_tuple_indices(has_concept, concept_id)), f'concept ids {filter_tuple_indices(self.concept_embed_ids, concept_id)} not found in ids passed in'
            concept_masks = filter_tuple_indices(concept_masks, concept_id)

        for concept_mask in concept_masks:
            x = x.masked_fill(concept_mask, 0)

        with torch.no_grad():
            embeds = self.embed(x)
            embeds.detach_()

        for concept, concept_mask in zip(self.concepts, concept_masks):
            embeds = torch.where(
                rearrange(concept_mask, '... -> ... 1'),
                concept,
                embeds
            )

        return embeds

@beartype
def merge_embedding_wrappers(
    *embeds: EmbeddingWrapper
) -> EmbeddingWrapper:

    total_concepts = sum([embed.num_concepts for embed in embeds])

    assert len(set([tuple(embed.embed.weight.shape) for embed in embeds])) == 1

    embed = embeds[0].embed

    merged_concepts = EmbeddingWrapper(
        embed = embed,
        num_concepts = total_concepts
    )

    concepts = torch.cat(tuple(embed.concepts.data for embed in embeds), dim = 0)

    merged_concepts.concepts = nn.Parameter(concepts)

    return merged_concepts
