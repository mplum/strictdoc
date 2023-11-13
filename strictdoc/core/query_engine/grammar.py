QUERY_GRAMMAR = r"""
Query:
 root_expression = BooleanExpression
;

AndExpression:
  '('
  expressions += BooleanExpression
  ('and' expressions += BooleanExpression)+
  ')'
;

OrExpression:
  '('
  expressions += BooleanExpression
  ('or' expressions += BooleanExpression)+
  ')'
;

NotExpression:
  'not'
  expression = BooleanExpression
;

BooleanExpression:
  AndExpression
  |
  OrExpression
  |
  NotExpression
  |
  NodeHasParentRequirementsExpression
  |
  NodeHasChildRequirementsExpression
  |
  InExpression
  |
  NotInExpression
  |
  NodeIsRequirementExpression
  |
  NodeIsSectionExpression
  |
  NodeIsRootExpression
  |
  EqualExpression
  |
  NotEqualExpression
;

StringExpression:
  '"' string = /[^"]+/ '"'
;

NoneExpression:
  _ = 'None'
;

NodeFieldExpression:
  'node["' field_name = /[A-Za-z0-9]+/ '"]'
;

NodeHasParentRequirementsExpression:
  _ = 'node.has_parent_requirements'
;

NodeHasChildRequirementsExpression:
  _ = 'node.has_child_requirements'
;

NodeIsRequirementExpression:
  _ = 'node.is_requirement'
;

NodeIsRootExpression:
  _ = 'node.is_root'
;

NodeIsSectionExpression:
  _ = 'node.is_section'
;

EqualExpression:
  lhs_expr = ComparableExpression '==' rhs_expr = ComparableExpression
;

NotEqualExpression:
  lhs_expr = ComparableExpression '!=' rhs_expr = ComparableExpression
;

ComparableExpression:
  NodeFieldExpression | StringExpression | NoneExpression
;

InExpression:
  lhs_expr = InableLHSExpression 'in' rhs_expr = InableRHSExpression
;

NotInExpression:
  lhs_expr = InableLHSExpression 'not in' rhs_expr = InableRHSExpression
;

InableLHSExpression:
  NodeFieldExpression | StringExpression
;

InableRHSExpression:
  NodeFieldExpression | StringExpression
;

"""