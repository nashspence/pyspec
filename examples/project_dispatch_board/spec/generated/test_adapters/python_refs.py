"""Generated contract references. Do not edit by hand."""

class Asset:
    ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE = 'asset.project.detail.ready.priority_badge'
    ASSET_PROJECT_LIST_EMPTY_ILLUSTRATION = 'asset.project.list.empty.illustration'

class AuthorizationPolicy:
    AUTHORIZATION_POLICY_PROJECT_APPROVE = 'authorization_policy.project.approve'
    AUTHORIZATION_POLICY_PROJECT_ARCHIVE = 'authorization_policy.project.archive'
    AUTHORIZATION_POLICY_PROJECT_CREATE = 'authorization_policy.project.create'
    AUTHORIZATION_POLICY_PROJECT_LIST = 'authorization_policy.project.list'
    AUTHORIZATION_POLICY_PROJECT_READ = 'authorization_policy.project.read'
    AUTHORIZATION_POLICY_PROJECT_SEND_APPROVAL_NOTICE = 'authorization_policy.project.send_approval_notice'
    AUTHORIZATION_POLICY_PROJECT_SUBMIT = 'authorization_policy.project.submit'

class CliCommand:
    CLI_COMMAND_PROJECT_APPROVE = 'cli_command.project.approve'
    CLI_COMMAND_PROJECT_BOARD = 'cli_command.project.board'

class CliResponseHandler:
    CLI_RESPONSE_HANDLER_CLI_PROJECT_APPROVE_APPROVED = 'cli_response_handler.cli.project.approve.approved'
    CLI_RESPONSE_HANDLER_CLI_PROJECT_APPROVE_FORBIDDEN = 'cli_response_handler.cli.project.approve.forbidden'
    CLI_RESPONSE_HANDLER_CLI_PROJECT_APPROVE_INVALID_STATE = 'cli_response_handler.cli.project.approve.invalid_state'
    CLI_RESPONSE_HANDLER_CLI_PROJECT_APPROVE_NOT_FOUND = 'cli_response_handler.cli.project.approve.not_found'
    CLI_RESPONSE_HANDLER_CLI_PROJECT_APPROVE_UNAUTHENTICATED = 'cli_response_handler.cli.project.approve.unauthenticated'
    CLI_RESPONSE_HANDLER_CLI_PROJECT_APPROVE_UNAVAILABLE = 'cli_response_handler.cli.project.approve.unavailable'

class ContentCase:
    CONTENT_CASE_PROJECT_DETAIL_HEADING_HIGH_PRIORITY = 'content_case.project.detail.heading.high_priority'
    CONTENT_CASE_PROJECT_DETAIL_PRIORITY_BADGE_HIGH_PRIORITY = 'content_case.project.detail.priority_badge.high_priority'

class Endpoint:
    ENDPOINT_PROJECT_APPROVE = 'endpoint.project.approve'
    ENDPOINT_PROJECT_CREATE = 'endpoint.project.create'
    ENDPOINT_PROJECT_LIST = 'endpoint.project.list'

class EntryPoint:
    ENTRY_POINT_API_PROJECT_APPROVE = 'entry_point.api.project.approve'
    ENTRY_POINT_API_PROJECT_CREATE = 'entry_point.api.project.create'
    ENTRY_POINT_API_PROJECT_LIST = 'entry_point.api.project.list'
    ENTRY_POINT_CLI_PROJECT_APPROVE = 'entry_point.cli.project.approve'
    ENTRY_POINT_CLI_PROJECT_BOARD = 'entry_point.cli.project.board'
    ENTRY_POINT_HTML_PROJECT_BOARD = 'entry_point.html.project.board'
    ENTRY_POINT_WORKER_PROJECT_APPROVAL_NOTICE = 'entry_point.worker.project.approval_notice'

class EntryPointDelegate:
    ENTRY_POINT_DELEGATE_CLI_PROJECT_APPROVE_TO_API_PROJECT_APPROVE = 'entry_point_delegate.cli.project.approve.to.api.project.approve'

class EntryPointTarget:
    ENTRY_POINT_TARGET_API_PROJECT_APPROVE_OPERATION_PROJECT_APPROVE = 'entry_point_target.api.project.approve.operation.project.approve'
    ENTRY_POINT_TARGET_API_PROJECT_CREATE_OPERATION_PROJECT_CREATE = 'entry_point_target.api.project.create.operation.project.create'
    ENTRY_POINT_TARGET_API_PROJECT_LIST_OPERATION_PROJECT_LIST = 'entry_point_target.api.project.list.operation.project.list'
    ENTRY_POINT_TARGET_CLI_PROJECT_APPROVE_ENTRY_POINT_API_PROJECT_APPROVE = 'entry_point_target.cli.project.approve.entry_point.api.project.approve'
    ENTRY_POINT_TARGET_CLI_PROJECT_BOARD_STATE_MACHINE_PROJECT_BOARD = 'entry_point_target.cli.project.board.state_machine.project.board'
    ENTRY_POINT_TARGET_HTML_PROJECT_BOARD_STATE_MACHINE_PROJECT_BOARD = 'entry_point_target.html.project.board.state_machine.project.board'
    ENTRY_POINT_TARGET_WORKER_PROJECT_APPROVAL_NOTICE_WORKFLOW_PROJECT_APPROVAL_NOTICE = 'entry_point_target.worker.project.approval_notice.workflow.project.approval_notice'

class Event:
    EVENT_PROJECT_APPROVED = 'event.project.approved'
    EVENT_PROJECT_ARCHIVED = 'event.project.archived'
    EVENT_PROJECT_CREATED = 'event.project.created'
    EVENT_PROJECT_SUBMITTED = 'event.project.submitted'

class Fact:
    FACT_PROJECT_DRAFT = 'fact.project.draft'
    FACT_PROJECT_SUBMITTED = 'fact.project.submitted'

class Fixture:
    FIXTURE_WORKSPACE_MEMBER = 'fixture.workspace.member'
    FIXTURE_WORKSPACE_REVIEWER = 'fixture.workspace.reviewer'

class Operation:
    OPERATION_PROJECT_APPROVE = 'operation.project.approve'
    OPERATION_PROJECT_ARCHIVE = 'operation.project.archive'
    OPERATION_PROJECT_CREATE = 'operation.project.create'
    OPERATION_PROJECT_LIST = 'operation.project.list'
    OPERATION_PROJECT_READ = 'operation.project.read'
    OPERATION_PROJECT_SEND_APPROVAL_NOTICE = 'operation.project.send_approval_notice'
    OPERATION_PROJECT_SUBMIT = 'operation.project.submit'

class Query:
    QUERY_PROJECT_ACTIVITY_READ = 'query.project.activity.read'
    QUERY_PROJECT_BOARD_LIST = 'query.project.board.list'
    QUERY_PROJECT_DETAIL_READ = 'query.project.detail.read'
    QUERY_PROJECT_LIST_LIST = 'query.project.list.list'

class RenderAuditCase:
    STATE_MACHINE_PROJECT_BOARD_READY_EMPTY_AUDIT = 'state_machine.project.board.ready.empty.audit'
    STATE_MACHINE_PROJECT_BOARD_READY_READY_SELECTED_AUDIT = 'state_machine.project.board.ready.ready_selected.audit'

class RenderProfile:
    RENDER_PROFILE_DEFAULT = 'render_profile.default'

class Route:
    ROUTE_PROJECT_BOARD = 'route.project.board'

class RuntimeResponse:
    RUNTIME_RESPONSE_CLI_PROJECT_APPROVE_APPROVED_STDOUT_PROJECT_ID = 'runtime_response.cli.project.approve.approved.stdout.project_id'
    RUNTIME_RESPONSE_CLI_PROJECT_APPROVE_FORBIDDEN_STDERR_MESSAGE = 'runtime_response.cli.project.approve.forbidden.stderr.message'
    RUNTIME_RESPONSE_CLI_PROJECT_APPROVE_INVALID_STATE_STDERR_MESSAGE = 'runtime_response.cli.project.approve.invalid_state.stderr.message'
    RUNTIME_RESPONSE_CLI_PROJECT_APPROVE_NOT_FOUND_STDERR_MESSAGE = 'runtime_response.cli.project.approve.not_found.stderr.message'
    RUNTIME_RESPONSE_CLI_PROJECT_APPROVE_UNAUTHENTICATED_STDERR_MESSAGE = 'runtime_response.cli.project.approve.unauthenticated.stderr.message'

class Screen:
    SCREEN_PROJECT_BOARD = 'screen.project.board'

class StateMachine:
    STATE_MACHINE_PROJECT_ACTIVITY = 'state_machine.project.activity'
    STATE_MACHINE_PROJECT_BOARD = 'state_machine.project.board'
    STATE_MACHINE_PROJECT_DETAIL = 'state_machine.project.detail'
    STATE_MACHINE_PROJECT_LIST = 'state_machine.project.list'

class Surface:
    STATE_MACHINE_PROJECT_ACTIVITY_EMPTY = 'state_machine.project.activity.empty'
    STATE_MACHINE_PROJECT_ACTIVITY_READY = 'state_machine.project.activity.ready'
    STATE_MACHINE_PROJECT_BOARD_READY = 'state_machine.project.board.ready'
    STATE_MACHINE_PROJECT_DETAIL_ERROR = 'state_machine.project.detail.error'
    STATE_MACHINE_PROJECT_DETAIL_LOADING = 'state_machine.project.detail.loading'
    STATE_MACHINE_PROJECT_DETAIL_NONE = 'state_machine.project.detail.none'
    STATE_MACHINE_PROJECT_DETAIL_READY = 'state_machine.project.detail.ready'
    STATE_MACHINE_PROJECT_LIST_EMPTY = 'state_machine.project.list.empty'
    STATE_MACHINE_PROJECT_LIST_ERROR = 'state_machine.project.list.error'
    STATE_MACHINE_PROJECT_LIST_LOADING = 'state_machine.project.list.loading'
    STATE_MACHINE_PROJECT_LIST_READY = 'state_machine.project.list.ready'

class TestCase:
    TEST_CASE_PROJECT_APPROVAL_NOTICE_WORKFLOW = 'test_case.project.approval_notice.workflow'
    TEST_CASE_PROJECT_APPROVE_FORBIDDEN = 'test_case.project.approve.forbidden'
    TEST_CASE_PROJECT_APPROVE_SUCCESS = 'test_case.project.approve.success'
    TEST_CASE_PROJECT_BOARD_EMPTY = 'test_case.project.board.empty'
    TEST_CASE_PROJECT_BOARD_READY = 'test_case.project.board.ready'
    TEST_CASE_PROJECT_CREATE_API_SUCCESS = 'test_case.project.create.api.success'

class Text:
    TEXT_PROJECT_ACTIVITY_EMPTY_BODY = 'text.project.activity.empty.body'
    TEXT_PROJECT_ACTIVITY_EMPTY_HEADING = 'text.project.activity.empty.heading'
    TEXT_PROJECT_ACTIVITY_READY_HEADING = 'text.project.activity.ready.heading'
    TEXT_PROJECT_APPROVE_FORBIDDEN = 'text.project.approve.forbidden'
    TEXT_PROJECT_APPROVE_INVALID_STATE = 'text.project.approve.invalid_state'
    TEXT_PROJECT_APPROVE_NOT_FOUND = 'text.project.approve.not_found'
    TEXT_PROJECT_APPROVE_SUCCESS = 'text.project.approve.success'
    TEXT_PROJECT_APPROVE_UNAUTHENTICATED = 'text.project.approve.unauthenticated'
    TEXT_PROJECT_APPROVE_UNAVAILABLE = 'text.project.approve.unavailable'
    TEXT_PROJECT_DETAIL_ERROR_BODY = 'text.project.detail.error.body'
    TEXT_PROJECT_DETAIL_ERROR_HEADING = 'text.project.detail.error.heading'
    TEXT_PROJECT_DETAIL_LOADING_MESSAGE = 'text.project.detail.loading.message'
    TEXT_PROJECT_DETAIL_NONE_BODY = 'text.project.detail.none.body'
    TEXT_PROJECT_DETAIL_NONE_HEADING = 'text.project.detail.none.heading'
    TEXT_PROJECT_DETAIL_READY_HEADING = 'text.project.detail.ready.heading'
    TEXT_PROJECT_LIST_EMPTY_BODY = 'text.project.list.empty.body'
    TEXT_PROJECT_LIST_EMPTY_HEADING = 'text.project.list.empty.heading'
    TEXT_PROJECT_LIST_ERROR_BODY = 'text.project.list.error.body'
    TEXT_PROJECT_LIST_ERROR_HEADING = 'text.project.list.error.heading'
    TEXT_PROJECT_LIST_LOADING_MESSAGE = 'text.project.list.loading.message'
    TEXT_PROJECT_LIST_READY_HEADING = 'text.project.list.ready.heading'

class Workflow:
    WORKFLOW_PROJECT_APPROVAL_NOTICE = 'workflow.project.approval_notice'
