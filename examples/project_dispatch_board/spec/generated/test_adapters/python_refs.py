"""Generated contract references. Do not edit by hand."""

class Asset:
    ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE = 'asset.project.detail.ready.priority_badge'
    ASSET_PROJECT_LIST_EMPTY_ILLUSTRATION = 'asset.project.list.empty.illustration'

class AuthorizationPolicy:
    AUTHORIZATION_POLICY_PROJECT_MEMBER = 'authorization_policy.project.member'
    AUTHORIZATION_POLICY_PROJECT_REVIEWER = 'authorization_policy.project.reviewer'

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

class LocalSignalRaise:
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_LOADING_QUERY_INVOCATION_READ_PROJECT_FORBIDDEN_DATA_SIGNAL_PROJECT_LOAD_FAILED = 'local_signal_raise.project.detail.loading.query_invocation.read_project.forbidden.data_signal.project_load_failed'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_LOADING_QUERY_INVOCATION_READ_PROJECT_FOUND_DATA_SIGNAL_PROJECT_LOADED = 'local_signal_raise.project.detail.loading.query_invocation.read_project.found.data_signal.project_loaded'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_LOADING_QUERY_INVOCATION_READ_PROJECT_NOT_FOUND_DATA_SIGNAL_PROJECT_LOAD_FAILED = 'local_signal_raise.project.detail.loading.query_invocation.read_project.not_found.data_signal.project_load_failed'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_LOADING_QUERY_INVOCATION_READ_PROJECT_UNAUTHENTICATED_DATA_SIGNAL_PROJECT_LOAD_FAILED = 'local_signal_raise.project.detail.loading.query_invocation.read_project.unauthenticated.data_signal.project_load_failed'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_OPERATION_INVOCATION_APPROVE_APPROVED_DATA_SIGNAL_PROJECT_CHANGED = 'local_signal_raise.project.detail.ready.operation_invocation.approve.approved.data_signal.project_changed'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_OPERATION_INVOCATION_APPROVE_INVALID_STATE_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.detail.ready.operation_invocation.approve.invalid_state.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_OPERATION_INVOCATION_ARCHIVE_ARCHIVED_DATA_SIGNAL_PROJECT_CHANGED = 'local_signal_raise.project.detail.ready.operation_invocation.archive.archived.data_signal.project_changed'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_OPERATION_INVOCATION_ARCHIVE_FORBIDDEN_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.detail.ready.operation_invocation.archive.forbidden.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_OPERATION_INVOCATION_ARCHIVE_INVALID_STATE_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.detail.ready.operation_invocation.archive.invalid_state.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_OPERATION_INVOCATION_ARCHIVE_NOT_FOUND_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.detail.ready.operation_invocation.archive.not_found.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_OPERATION_INVOCATION_ARCHIVE_UNAUTHENTICATED_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.detail.ready.operation_invocation.archive.unauthenticated.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_QUERY_INVOCATION_READ_PROJECT_FORBIDDEN_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.detail.ready.query_invocation.read_project.forbidden.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_QUERY_INVOCATION_READ_PROJECT_NOT_FOUND_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.detail.ready.query_invocation.read_project.not_found.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_DETAIL_READY_QUERY_INVOCATION_READ_PROJECT_UNAUTHENTICATED_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.detail.ready.query_invocation.read_project.unauthenticated.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_EMPTY_OPERATION_INVOCATION_CREATE_CREATED_DATA_SIGNAL_PROJECTS_CHANGED = 'local_signal_raise.project.list.empty.operation_invocation.create.created.data_signal.projects_changed'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_EMPTY_OPERATION_INVOCATION_CREATE_VALIDATION_FAILED_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.list.empty.operation_invocation.create.validation_failed.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_QUERY_INVOCATION_LIST_PROJECTS_FORBIDDEN_DATA_SIGNAL_PROJECT_LIST_FAILED = 'local_signal_raise.project.list.query_invocation.list_projects.forbidden.data_signal.project_list_failed'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_QUERY_INVOCATION_LIST_PROJECTS_LISTED_DATA_SIGNAL_PROJECTS_LOADED = 'local_signal_raise.project.list.query_invocation.list_projects.listed.data_signal.projects_loaded'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_QUERY_INVOCATION_LIST_PROJECTS_UNAUTHENTICATED_DATA_SIGNAL_PROJECT_LIST_FAILED = 'local_signal_raise.project.list.query_invocation.list_projects.unauthenticated.data_signal.project_list_failed'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_QUERY_INVOCATION_LIST_PROJECTS_UNAVAILABLE_DATA_SIGNAL_PROJECT_LIST_FAILED = 'local_signal_raise.project.list.query_invocation.list_projects.unavailable.data_signal.project_list_failed'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_READY_OPERATION_INVOCATION_CREATE_CREATED_DATA_SIGNAL_PROJECTS_CHANGED = 'local_signal_raise.project.list.ready.operation_invocation.create.created.data_signal.projects_changed'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_READY_OPERATION_INVOCATION_SUBMIT_FORBIDDEN_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.list.ready.operation_invocation.submit.forbidden.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_READY_OPERATION_INVOCATION_SUBMIT_INVALID_STATE_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.list.ready.operation_invocation.submit.invalid_state.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_READY_OPERATION_INVOCATION_SUBMIT_NOT_FOUND_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.list.ready.operation_invocation.submit.not_found.message.show_invalid_state'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_READY_OPERATION_INVOCATION_SUBMIT_SUBMITTED_DATA_SIGNAL_PROJECTS_CHANGED = 'local_signal_raise.project.list.ready.operation_invocation.submit.submitted.data_signal.projects_changed'
    LOCAL_SIGNAL_RAISE_PROJECT_LIST_READY_OPERATION_INVOCATION_SUBMIT_UNAUTHENTICATED_MESSAGE_SHOW_INVALID_STATE = 'local_signal_raise.project.list.ready.operation_invocation.submit.unauthenticated.message.show_invalid_state'

class Operation:
    OPERATION_PROJECT_APPROVE = 'operation.project.approve'
    OPERATION_PROJECT_ARCHIVE = 'operation.project.archive'
    OPERATION_PROJECT_CREATE = 'operation.project.create'
    OPERATION_PROJECT_LIST = 'operation.project.list'
    OPERATION_PROJECT_READ = 'operation.project.read'
    OPERATION_PROJECT_SEND_APPROVAL_NOTICE = 'operation.project.send_approval_notice'
    OPERATION_PROJECT_SUBMIT = 'operation.project.submit'

class OperationInvocation:
    OPERATION_INVOCATION_PROJECT_DETAIL_READY_APPROVE = 'operation_invocation.project.detail.ready.approve'
    OPERATION_INVOCATION_PROJECT_DETAIL_READY_ARCHIVE = 'operation_invocation.project.detail.ready.archive'
    OPERATION_INVOCATION_PROJECT_LIST_EMPTY_CREATE = 'operation_invocation.project.list.empty.create'
    OPERATION_INVOCATION_PROJECT_LIST_READY_CREATE = 'operation_invocation.project.list.ready.create'
    OPERATION_INVOCATION_PROJECT_LIST_READY_SUBMIT = 'operation_invocation.project.list.ready.submit'

class OperationOutcomeRoute:
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_APPROVE_APPROVED = 'operation_outcome_route.project.detail.ready.approve.approved'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_APPROVE_FORBIDDEN = 'operation_outcome_route.project.detail.ready.approve.forbidden'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_APPROVE_INVALID_STATE = 'operation_outcome_route.project.detail.ready.approve.invalid_state'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_APPROVE_NOT_FOUND = 'operation_outcome_route.project.detail.ready.approve.not_found'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_APPROVE_UNAUTHENTICATED = 'operation_outcome_route.project.detail.ready.approve.unauthenticated'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_APPROVE_UNAVAILABLE = 'operation_outcome_route.project.detail.ready.approve.unavailable'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_ARCHIVE_ARCHIVED = 'operation_outcome_route.project.detail.ready.archive.archived'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_ARCHIVE_FORBIDDEN = 'operation_outcome_route.project.detail.ready.archive.forbidden'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_ARCHIVE_INVALID_STATE = 'operation_outcome_route.project.detail.ready.archive.invalid_state'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_ARCHIVE_NOT_FOUND = 'operation_outcome_route.project.detail.ready.archive.not_found'
    OPERATION_OUTCOME_ROUTE_PROJECT_DETAIL_READY_ARCHIVE_UNAUTHENTICATED = 'operation_outcome_route.project.detail.ready.archive.unauthenticated'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_EMPTY_CREATE_CREATED = 'operation_outcome_route.project.list.empty.create.created'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_EMPTY_CREATE_FORBIDDEN = 'operation_outcome_route.project.list.empty.create.forbidden'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_EMPTY_CREATE_UNAUTHENTICATED = 'operation_outcome_route.project.list.empty.create.unauthenticated'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_EMPTY_CREATE_VALIDATION_FAILED = 'operation_outcome_route.project.list.empty.create.validation_failed'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_CREATE_CREATED = 'operation_outcome_route.project.list.ready.create.created'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_CREATE_FORBIDDEN = 'operation_outcome_route.project.list.ready.create.forbidden'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_CREATE_UNAUTHENTICATED = 'operation_outcome_route.project.list.ready.create.unauthenticated'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_CREATE_VALIDATION_FAILED = 'operation_outcome_route.project.list.ready.create.validation_failed'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_SUBMIT_FORBIDDEN = 'operation_outcome_route.project.list.ready.submit.forbidden'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_SUBMIT_INVALID_STATE = 'operation_outcome_route.project.list.ready.submit.invalid_state'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_SUBMIT_NOT_FOUND = 'operation_outcome_route.project.list.ready.submit.not_found'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_SUBMIT_SUBMITTED = 'operation_outcome_route.project.list.ready.submit.submitted'
    OPERATION_OUTCOME_ROUTE_PROJECT_LIST_READY_SUBMIT_UNAUTHENTICATED = 'operation_outcome_route.project.list.ready.submit.unauthenticated'

class QueryInvocation:
    QUERY_INVOCATION_PROJECT_ACTIVITY_READY_READ_ACTIVITY = 'query_invocation.project.activity.ready.read_activity'
    QUERY_INVOCATION_PROJECT_BOARD_LIST_BOARD = 'query_invocation.project.board.list_board'
    QUERY_INVOCATION_PROJECT_DETAIL_LOADING_READ_PROJECT = 'query_invocation.project.detail.loading.read_project'
    QUERY_INVOCATION_PROJECT_DETAIL_READY_READ_PROJECT = 'query_invocation.project.detail.ready.read_project'
    QUERY_INVOCATION_PROJECT_LIST_LIST_PROJECTS = 'query_invocation.project.list.list_projects'

class QueryOutcomeRoute:
    QUERY_OUTCOME_ROUTE_PROJECT_ACTIVITY_READY_READ_ACTIVITY_FORBIDDEN = 'query_outcome_route.project.activity.ready.read_activity.forbidden'
    QUERY_OUTCOME_ROUTE_PROJECT_ACTIVITY_READY_READ_ACTIVITY_FOUND = 'query_outcome_route.project.activity.ready.read_activity.found'
    QUERY_OUTCOME_ROUTE_PROJECT_ACTIVITY_READY_READ_ACTIVITY_NOT_FOUND = 'query_outcome_route.project.activity.ready.read_activity.not_found'
    QUERY_OUTCOME_ROUTE_PROJECT_ACTIVITY_READY_READ_ACTIVITY_UNAUTHENTICATED = 'query_outcome_route.project.activity.ready.read_activity.unauthenticated'
    QUERY_OUTCOME_ROUTE_PROJECT_BOARD_LIST_BOARD_FORBIDDEN = 'query_outcome_route.project.board.list_board.forbidden'
    QUERY_OUTCOME_ROUTE_PROJECT_BOARD_LIST_BOARD_LISTED = 'query_outcome_route.project.board.list_board.listed'
    QUERY_OUTCOME_ROUTE_PROJECT_BOARD_LIST_BOARD_UNAUTHENTICATED = 'query_outcome_route.project.board.list_board.unauthenticated'
    QUERY_OUTCOME_ROUTE_PROJECT_BOARD_LIST_BOARD_UNAVAILABLE = 'query_outcome_route.project.board.list_board.unavailable'
    QUERY_OUTCOME_ROUTE_PROJECT_DETAIL_LOADING_READ_PROJECT_FORBIDDEN = 'query_outcome_route.project.detail.loading.read_project.forbidden'
    QUERY_OUTCOME_ROUTE_PROJECT_DETAIL_LOADING_READ_PROJECT_FOUND = 'query_outcome_route.project.detail.loading.read_project.found'
    QUERY_OUTCOME_ROUTE_PROJECT_DETAIL_LOADING_READ_PROJECT_NOT_FOUND = 'query_outcome_route.project.detail.loading.read_project.not_found'
    QUERY_OUTCOME_ROUTE_PROJECT_DETAIL_LOADING_READ_PROJECT_UNAUTHENTICATED = 'query_outcome_route.project.detail.loading.read_project.unauthenticated'
    QUERY_OUTCOME_ROUTE_PROJECT_DETAIL_READY_READ_PROJECT_FORBIDDEN = 'query_outcome_route.project.detail.ready.read_project.forbidden'
    QUERY_OUTCOME_ROUTE_PROJECT_DETAIL_READY_READ_PROJECT_FOUND = 'query_outcome_route.project.detail.ready.read_project.found'
    QUERY_OUTCOME_ROUTE_PROJECT_DETAIL_READY_READ_PROJECT_NOT_FOUND = 'query_outcome_route.project.detail.ready.read_project.not_found'
    QUERY_OUTCOME_ROUTE_PROJECT_DETAIL_READY_READ_PROJECT_UNAUTHENTICATED = 'query_outcome_route.project.detail.ready.read_project.unauthenticated'
    QUERY_OUTCOME_ROUTE_PROJECT_LIST_LIST_PROJECTS_FORBIDDEN = 'query_outcome_route.project.list.list_projects.forbidden'
    QUERY_OUTCOME_ROUTE_PROJECT_LIST_LIST_PROJECTS_LISTED = 'query_outcome_route.project.list.list_projects.listed'
    QUERY_OUTCOME_ROUTE_PROJECT_LIST_LIST_PROJECTS_UNAUTHENTICATED = 'query_outcome_route.project.list.list_projects.unauthenticated'
    QUERY_OUTCOME_ROUTE_PROJECT_LIST_LIST_PROJECTS_UNAVAILABLE = 'query_outcome_route.project.list.list_projects.unavailable'

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
