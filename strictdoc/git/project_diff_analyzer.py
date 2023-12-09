import hashlib
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union

from strictdoc.backend.sdoc.models.document import Document
from strictdoc.backend.sdoc.models.reference import (
    ParentReqReference,
)
from strictdoc.backend.sdoc.models.requirement import (
    Requirement,
    RequirementField,
)
from strictdoc.backend.sdoc.models.section import Section
from strictdoc.core.document_iterator import DocumentCachingIterator
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.git.change import (
    ChangeUnionType,
    RequirementChange,
    RequirementFieldChange,
    SectionChange,
)
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.diff import get_colored_diff_string, similar
from strictdoc.helpers.md5 import get_md5
from strictdoc.helpers.mid import MID


def calculate_similarity(lhs: Requirement, rhs: Requirement) -> float:
    similar_fields = []
    for field_name_, field_values_ in lhs.ordered_fields_lookup.items():
        if field_name_ == "COMMENT":
            continue

        if field_name_ not in rhs.ordered_fields_lookup:
            continue

        if field_name_ not in ("TITLE", "STATEMENT", "RATIONALE"):
            continue

        rhs_field_values = rhs.ordered_fields_lookup[field_name_]

        lhs_field_value = (
            field_values_[0].field_value
            if field_values_[0].field_value is not None
            else field_values_[0].field_value_multiline
        )
        rhs_field_value = (
            rhs_field_values[0].field_value
            if rhs_field_values[0].field_value is not None
            else rhs_field_values[0].field_value_multiline
        )

        similar_fields.append(similar(lhs_field_value, rhs_field_value))

    return statistics.mean(similar_fields)


@dataclass
class ProjectTreeDiffStats:
    document_md5_hashes: Set[str] = field(default_factory=set)
    requirement_md5_hashes: Set[str] = field(default_factory=set)
    section_md5_hashes: Set[str] = field(default_factory=set)
    free_text_md5_hashes: Set[str] = field(default_factory=set)
    map_nodes_to_hashes: Dict[Any, str] = field(default_factory=dict)
    map_uid_to_nodes: Dict[str, Any] = field(default_factory=dict)
    map_titles_to_nodes: Dict[str, List] = field(default_factory=dict)
    map_statements_to_nodes: Dict[str, Any] = field(default_factory=dict)
    map_rel_paths_to_docs: Dict[str, Document] = field(default_factory=dict)

    cache_requirement_to_requirement: Dict[Requirement, Requirement] = field(
        default_factory=dict
    )

    def get_md5_by_node(self, node) -> str:
        return self.map_nodes_to_hashes[node]

    def contains_requirement_md5(self, requirement_md5: str) -> bool:
        return requirement_md5 in self.requirement_md5_hashes

    def contains_free_text_md5(self, free_text_md5: str) -> bool:
        return free_text_md5 in self.free_text_md5_hashes

    def contains_section_md5(self, section_md5: str) -> bool:
        return section_md5 in self.section_md5_hashes

    def contains_document_md5(self, document_md5: str) -> bool:
        return document_md5 in self.document_md5_hashes

    def contains_requirement_field(
        self, requirement: Requirement, field_name: str, field_value: str
    ):
        assert isinstance(field_value, str)
        other_requirement: Optional[Requirement] = self.find_requirement(
            requirement
        )
        if other_requirement is None:
            return False

        if field_name not in other_requirement.ordered_fields_lookup:
            return False

        other_requirement_fields = other_requirement.ordered_fields_lookup[
            field_name
        ]
        for field_ in other_requirement_fields:
            if field_.field_value == field_value:
                return True
            if field_.field_value_multiline == field_value:
                return True
        return False

    def get_identical_requirement_field(
        self, requirement: Requirement, field_name: str, field_value: str
    ) -> Optional[RequirementField]:
        assert isinstance(field_value, str)
        other_requirement: Optional[Requirement] = self.find_requirement(
            requirement
        )
        if other_requirement is None:
            return None

        if field_name not in other_requirement.ordered_fields_lookup:
            return None

        other_requirement_fields = other_requirement.ordered_fields_lookup[
            field_name
        ]
        for field_ in other_requirement_fields:
            if field_.field_value == field_value:
                return field_
            if field_.field_value_multiline == field_value:
                return field_
        return None

    def get_diffed_free_text(self, node: Union[Section, Document], side: str):
        assert isinstance(node, (Section, Document))
        assert side in ("left", "right")

        if isinstance(node, Document):
            document: Document = assert_cast(node, Document)

            other_document_or_none: Optional[
                Document
            ] = self.map_rel_paths_to_docs.get(
                document.meta.input_doc_full_path
            )
            if other_document_or_none is None:
                return None
            other_document: Document = assert_cast(
                other_document_or_none, Document
            )
            if len(other_document.free_texts) == 0:
                return None
            document_free_text = document.free_texts[0]
            other_document_free_text = other_document.free_texts[0]
            document_free_text_parts = (
                document_free_text.get_parts_as_text_escaped()
            )
            other_document_free_text_parts = (
                other_document_free_text.get_parts_as_text_escaped()
            )
            if side == "left":
                return get_colored_diff_string(
                    document_free_text_parts,
                    other_document_free_text_parts,
                    side,
                )
            else:
                return get_colored_diff_string(
                    other_document_free_text_parts,
                    document_free_text_parts,
                    side,
                )

        if isinstance(node, Section):
            section: Section = assert_cast(node, Section)
            section_free_text = section.free_texts[0]
            section_free_text_parts = (
                section_free_text.get_parts_as_text_escaped()
            )

            if section.reserved_uid is not None:
                other_section_or_none: Optional[
                    Section
                ] = self.map_uid_to_nodes.get(section.reserved_uid)
                if other_section_or_none is not None:
                    other_section: Section = assert_cast(
                        other_section_or_none, Section
                    )

                    if len(other_section.free_texts) > 0:
                        other_section_free_text = other_section.free_texts[0]
                        other_section_free_text_parts = (
                            other_section_free_text.get_parts_as_text_escaped()
                        )

                        if side == "left":
                            return get_colored_diff_string(
                                section_free_text_parts,
                                other_section_free_text_parts,
                                side,
                            )
                        else:
                            return get_colored_diff_string(
                                other_section_free_text_parts,
                                section_free_text_parts,
                                side,
                            )
                    else:
                        if side == "left":
                            return get_colored_diff_string(
                                section_free_text_parts, "", side
                            )
                        else:
                            return get_colored_diff_string(
                                "", section_free_text_parts, side
                            )
                else:
                    return None

            # Section does not have a UID. We can still try to find a section
            # with the same title if it still exists in the same parent
            # section/document scope.
            else:
                pass

        return None

    def get_diffed_requirement_field(
        self,
        requirement: Requirement,
        field_name: str,
        field_value: str,
        side: str,
    ):
        assert isinstance(field_value, str)
        assert side in ("left", "right")

        other_requirement: Optional[Requirement] = self.find_requirement(
            requirement
        )
        if (
            other_requirement is None
            or field_name not in other_requirement.ordered_fields_lookup
        ):
            return field_value

        other_requirement_fields = other_requirement.ordered_fields_lookup[
            field_name
        ]

        other_field_value = None
        for field_ in other_requirement_fields:
            if field_.field_value is not None:
                other_field_value = field_.field_value
                break
            if field_.field_value_multiline is not None:
                other_field_value = field_.field_value_multiline
                break
        assert other_field_value is not None

        if side == "left":
            colored_field_value = get_colored_diff_string(
                field_value, other_field_value, side
            )
            return colored_field_value
        else:
            colored_field_value = get_colored_diff_string(
                other_field_value, field_value, side
            )
            return colored_field_value

    def contains_requirement_relations(
        self,
        requirement: Requirement,
        relation_uid: str,
        relation_role: Optional[str],
    ):
        other_requirement: Optional[Requirement] = self.find_requirement(
            requirement
        )
        if other_requirement is None:
            return False
        for reference_ in other_requirement.references:
            if isinstance(reference_, ParentReqReference):
                parent_reference: ParentReqReference = assert_cast(
                    reference_, ParentReqReference
                )
                if (
                    parent_reference.ref_uid == relation_uid
                    and parent_reference.role == relation_role
                ):
                    return True
        return False

    def find_requirement(
        self, requirement: Requirement
    ) -> Optional[Requirement]:
        if requirement in self.cache_requirement_to_requirement:
            return self.cache_requirement_to_requirement[requirement]

        requirement_parent_uids = set()
        for parent_ in requirement.references:
            if isinstance(parent_, ParentReqReference):
                requirement_parent_uids.add(parent_.ref_uid)

        if (
            requirement.reserved_uid is None
            or requirement.reserved_uid not in self.map_uid_to_nodes
        ):
            candidate_requirements: Dict[Requirement, float] = {}

            if (
                requirement.reserved_title is not None
                and requirement.reserved_title in self.map_titles_to_nodes
            ):
                other_requirements = self.map_titles_to_nodes[
                    requirement.reserved_title
                ]
                for other_requirement_ in other_requirements:
                    if (
                        not other_requirement_.reserved_uid
                        in requirement_parent_uids
                    ):
                        candidate_requirements[other_requirement_] = 0

            for candidate_requirement_ in candidate_requirements.keys():
                candidate_requirements[
                    candidate_requirement_
                ] = calculate_similarity(requirement, candidate_requirement_)

            if len(candidate_requirements) > 0:
                candidate_requirement = max(
                    candidate_requirements, key=candidate_requirements.get
                )
                self.cache_requirement_to_requirement[
                    requirement
                ] = candidate_requirement
                return candidate_requirement
            return None

        other_requirement: Requirement = self.map_uid_to_nodes[
            requirement.reserved_uid
        ]
        return other_requirement


@dataclass
class ChangeStats:
    map_requirements_to_tokens: Dict[Requirement, str] = field(
        default_factory=dict
    )
    changes: List[ChangeUnionType] = field(default_factory=list)
    map_nodes_to_changes: Dict[Any, ChangeUnionType] = field(
        default_factory=dict
    )

    def find_change(self, node: Any):
        return self.map_nodes_to_changes.get(node)

    def find_requirement_token(self, requirement: Requirement) -> Optional[str]:
        return self.map_requirements_to_tokens.get(requirement)

    @staticmethod
    def create_from_two_indexes(
        lhs_index: TraceabilityIndex,
        rhs_index: TraceabilityIndex,
        lhs_stats: ProjectTreeDiffStats,
        rhs_stats: ProjectTreeDiffStats,
    ):
        stats = ChangeStats()

        ChangeStats._iterate_one_index(
            lhs_index, lhs_stats, rhs_stats, stats, "left"
        )
        ChangeStats._iterate_one_index(
            rhs_index, rhs_stats, lhs_stats, stats, "right"
        )

        return stats

    @staticmethod
    def _iterate_one_index(
        index: TraceabilityIndex,
        self_stats: ProjectTreeDiffStats,
        other_stats: ProjectTreeDiffStats,
        change_stats: "ChangeStats",
        side: str,
    ):
        assert side in ("left", "right")

        for document in index.document_tree.document_list:
            document_iterator = DocumentCachingIterator(document)

            for node in document_iterator.all_content():
                if isinstance(node, Section):
                    section_md5 = self_stats.get_md5_by_node(node)
                    section_modified = not other_stats.contains_section_md5(
                        section_md5
                    )
                    if section_modified:
                        matched_uid: Optional[str] = None
                        if node.reserved_uid is not None:
                            assert len(node.reserved_uid) > 0
                            if other_stats.map_uid_to_nodes.get(
                                node.reserved_uid
                            ):
                                matched_uid = node.reserved_uid

                        free_text_modified = False
                        colored_free_text_diff: Optional[str] = None
                        if len(node.free_texts) > 0:
                            free_text = node.free_texts[0]
                            free_text_md5 = self_stats.get_md5_by_node(
                                free_text
                            )
                            free_text_modified = (
                                not other_stats.contains_free_text_md5(
                                    free_text_md5
                                )
                            )
                            colored_free_text_diff = (
                                other_stats.get_diffed_free_text(node, side)
                            )

                        section_change: SectionChange = SectionChange(
                            matched_uid=matched_uid,
                            free_text_modified=free_text_modified,
                            colored_free_text_diff=colored_free_text_diff,
                        )
                        change_stats.map_nodes_to_changes[node] = section_change
                        change_stats.changes.append(section_change)

                if isinstance(node, Requirement):
                    """
                    Step: We check if a requirement was modified at all, or if
                    it has already been checked before. Skipping the requirement
                    if there is nothing to do.
                    """
                    # FIXME: Is this 100% valid?

                    if node in change_stats.map_nodes_to_changes:
                        continue

                    if node in change_stats.map_requirements_to_tokens:
                        continue

                    requirement: Requirement = assert_cast(node, Requirement)
                    requirement_md5 = self_stats.get_md5_by_node(requirement)
                    requirement_modified = (
                        not other_stats.contains_requirement_md5(
                            requirement_md5
                        )
                    )
                    if not requirement_modified:
                        continue

                    other_requirement_or_none: Optional[
                        Requirement
                    ] = other_stats.find_requirement(requirement)

                    # If there is no other requirement to compare with,
                    # we simply record this as a trivial change where everything
                    # is tracked as "deleted" or "new".
                    if other_requirement_or_none is None:
                        requirement_change: RequirementChange = (
                            RequirementChange(
                                requirement_token=None,
                                field_changes=[],
                            )
                        )
                        change_stats.map_nodes_to_changes[
                            node
                        ] = requirement_change
                        change_stats.changes.append(requirement_change)
                        continue

                    """
                    Step: Starting from here, we will be looking at the
                    difference between this and the other requirement.
                    """
                    other_requirement: Requirement = other_requirement_or_none

                    field_changes: List[RequirementFieldChange] = []

                    """
                    Step: Create a requirement token that is used by JS to match
                    the LHS nodes with RHS nodes.
                    """
                    requirement_token: str = MID.create().get_string_value()
                    change_stats.map_requirements_to_tokens[
                        requirement
                    ] = requirement_token
                    change_stats.map_requirements_to_tokens[
                        other_requirement
                    ] = requirement_token

                    """
                    Iterate over requirement fields.
                    """
                    requirement_fields_iter = iter(
                        requirement.enumerate_all_fields()
                    )
                    other_requirement_fields_iter = iter(
                        other_requirement.enumerate_all_fields()
                    )

                    field_checked_so_far: Set[RequirementField] = set()
                    while True:
                        requirement_field_tripple = next(
                            requirement_fields_iter, None
                        )
                        if (
                            requirement_field_tripple is not None
                            and requirement_field_tripple[0]
                            not in field_checked_so_far
                        ):
                            requirement_field_change = ChangeStats.create_field_change(
                                self_stats=self_stats,
                                other_stats=other_stats,
                                requirement=requirement,
                                requirement_field=requirement_field_tripple[0],
                                other_requirement=other_requirement,
                                requirement_field_name=requirement_field_tripple[
                                    1
                                ],
                                requirement_field_value=requirement_field_tripple[
                                    2
                                ],
                            )
                            if requirement_field_change is not None:
                                field_changes.append(requirement_field_change)
                                if (
                                    requirement_field_change.lhs_field
                                    is not None
                                ):
                                    field_checked_so_far.add(
                                        requirement_field_change.lhs_field
                                    )
                                if (
                                    requirement_field_change.rhs_field
                                    is not None
                                ):
                                    field_checked_so_far.add(
                                        requirement_field_change.rhs_field
                                    )
                            else:
                                field_checked_so_far.add(
                                    requirement_field_tripple[0]
                                )

                        other_requirement_field_tripple = next(
                            other_requirement_fields_iter, None
                        )
                        if (
                            other_requirement_field_tripple is not None
                            and other_requirement_field_tripple[0]
                            not in field_checked_so_far
                        ):
                            requirement_field_change = ChangeStats.create_field_change(
                                self_stats=other_stats,
                                other_stats=self_stats,
                                requirement=other_requirement,
                                requirement_field=other_requirement_field_tripple[
                                    0
                                ],
                                other_requirement=requirement,
                                requirement_field_name=other_requirement_field_tripple[
                                    1
                                ],
                                requirement_field_value=other_requirement_field_tripple[
                                    2
                                ],
                            )
                            if requirement_field_change is not None:
                                field_changes.append(requirement_field_change)
                                if (
                                    requirement_field_change.lhs_field
                                    is not None
                                ):
                                    field_checked_so_far.add(
                                        requirement_field_change.lhs_field
                                    )
                                if (
                                    requirement_field_change.rhs_field
                                    is not None
                                ):
                                    field_checked_so_far.add(
                                        requirement_field_change.rhs_field
                                    )
                            else:
                                field_checked_so_far.add(
                                    other_requirement_field_tripple[0]
                                )

                        if (
                            requirement_field_tripple is None
                            and other_requirement_field_tripple is None
                        ):
                            break

                    requirement_change: RequirementChange = RequirementChange(
                        requirement_token=requirement_token,
                        field_changes=field_changes,
                    )
                    change_stats.map_nodes_to_changes[node] = requirement_change
                    if other_requirement_or_none is not None:
                        change_stats.map_nodes_to_changes[
                            other_requirement_or_none
                        ] = requirement_change
                    change_stats.changes.append(requirement_change)

    @staticmethod
    def create_field_change(
        *,
        self_stats: ProjectTreeDiffStats,
        other_stats: ProjectTreeDiffStats,
        requirement: Requirement,
        requirement_field: RequirementField,
        other_requirement: Requirement,
        requirement_field_name: str,
        requirement_field_value: str,
    ) -> Optional[RequirementFieldChange]:
        assert isinstance(requirement, Requirement)
        assert isinstance(requirement_field, RequirementField)
        assert isinstance(other_requirement, Requirement)

        other_requirement_field = other_stats.get_identical_requirement_field(
            requirement, requirement_field_name, requirement_field_value
        )
        # If there is an identical field, it means the field
        # is not modified. Nothing to do.
        if other_requirement_field is not None:
            return None

        left_diff = other_stats.get_diffed_requirement_field(
            requirement, requirement_field_name, requirement_field_value, "left"
        )
        right_diff = self_stats.get_diffed_requirement_field(
            other_requirement,
            requirement_field_name,
            requirement_field_value,
            "right",
        )
        return RequirementFieldChange(
            field_name=requirement_field_name,
            lhs_field=requirement_field,
            rhs_field=other_requirement_field,
            left_diff=left_diff,
            right_diff=right_diff,
        )


class ProjectDiffAnalyzer:
    @staticmethod
    def analyze_document_tree(
        traceability_index: TraceabilityIndex,
    ) -> ProjectTreeDiffStats:
        document_tree_stats: ProjectTreeDiffStats = ProjectTreeDiffStats()

        for document in traceability_index.document_tree.document_list:
            ProjectDiffAnalyzer.analyze_document(document, document_tree_stats)

        return document_tree_stats

    @staticmethod
    def analyze_document(
        document: Document,
        document_tree_stats: ProjectTreeDiffStats,
    ) -> None:
        document_iterator = DocumentCachingIterator(document)

        map_nodes_to_hashers: Dict[Any, Any] = {document: hashlib.md5()}

        document_tree_stats.map_rel_paths_to_docs[
            document.meta.input_doc_full_path
        ] = document

        # Document's top level free text.
        if len(document.free_texts) > 0:
            free_text = document.free_texts[0]
            free_text_text = document.free_texts[0].get_parts_as_text()
            free_text_md5 = get_md5(free_text_text)
            document_tree_stats.free_text_md5_hashes.add(free_text_md5)
            document_tree_stats.map_nodes_to_hashes[free_text] = free_text_md5

        for node in document_iterator.all_content():
            if isinstance(node, Section):
                if node.reserved_uid is not None:
                    document_tree_stats.map_uid_to_nodes[
                        node.reserved_uid
                    ] = node
                hasher = hashlib.md5()
                hasher.update(node.title.encode("utf-8"))
                if len(node.free_texts) > 0:
                    free_text = node.free_texts[0]
                    free_text_text = node.free_texts[0].get_parts_as_text()
                    free_text_md5 = get_md5(free_text_text)
                    document_tree_stats.free_text_md5_hashes.add(free_text_md5)
                    document_tree_stats.map_nodes_to_hashes[
                        free_text
                    ] = free_text_md5

                    hasher.update(free_text_text.encode("utf-8"))
                map_nodes_to_hashers[node] = hasher

            elif isinstance(node, Requirement):
                if node.reserved_uid is not None:
                    document_tree_stats.map_uid_to_nodes[
                        node.reserved_uid
                    ] = node

                hasher = hashlib.md5()
                for (
                    field_name_,
                    field_values_,
                ) in node.ordered_fields_lookup.items():
                    requirement_field: RequirementField = field_values_[0]
                    if field_name_ == "TITLE":
                        this_title_requirements = (
                            document_tree_stats.map_titles_to_nodes.setdefault(
                                requirement_field.field_value, []
                            )
                        )
                        this_title_requirements.append(node)
                    elif field_name_ == "STATEMENT":
                        statement_value: str = assert_cast(
                            requirement_field.field_value
                            if requirement_field.field_value is not None
                            else requirement_field.field_value_multiline,
                            str,
                        )
                        document_tree_stats.map_statements_to_nodes[
                            statement_value
                        ] = node

                    if requirement_field.field_value is not None:
                        hasher.update(
                            requirement_field.field_value.encode("utf-8")
                        )
                    elif requirement_field.field_value_multiline is not None:
                        hasher.update(
                            requirement_field.field_value_multiline.encode(
                                "utf-8"
                            )
                        )
                    else:
                        # WIP
                        continue
                map_nodes_to_hashers[node] = hasher
            else:
                raise AssertionError

        def recurse(node):
            assert isinstance(node, (Section, Document))
            for subnode in node.section_contents:
                if isinstance(subnode, Section):
                    map_nodes_to_hashers[node].update(recurse(subnode))
                elif isinstance(subnode, Requirement):
                    node_md5 = (
                        map_nodes_to_hashers[subnode]
                        .hexdigest()
                        .encode("utf-8")
                    )
                    map_nodes_to_hashers[node].update(node_md5)
            return map_nodes_to_hashers[node].hexdigest().encode("utf-8")

        # Keeping this code in case we will need to include child node hashes
        # to parent node hashes recursively. This was the original
        # implementation which we discarded. Now, each node's hash is
        # self-contained.
        # recurse(document)  # noqa: ERA001

        for node_ in document_iterator.all_content():
            node_md5 = map_nodes_to_hashers[node_].hexdigest().encode("utf-8")
            map_nodes_to_hashers[document].update(node_md5)

        for node_, node_hasher_ in map_nodes_to_hashers.items():
            node_md5 = node_hasher_.hexdigest()
            document_tree_stats.map_nodes_to_hashes[node_] = node_md5

            if isinstance(node_, Section):
                document_tree_stats.section_md5_hashes.add(node_md5)
            elif isinstance(node_, Requirement):
                document_tree_stats.requirement_md5_hashes.add(node_md5)
            elif isinstance(node_, Document):
                document_tree_stats.document_md5_hashes.add(node_md5)
