"""Regression coverage for observed search, browser filling, and monitor failures."""
import json
from urllib.parse import parse_qs, urlsplit

from backend.src.tools.tsenta_hiringcafe import (
    _search_url, job_matches_standing_instructions, rank_hiringcafe_jobs,
)
from backend.src.tools.tsenta_llm import make_llm_answerer
from backend.src.tools.tsenta_apply import collect_fields, answer_fields, _execute_actions
from backend.src.tools.tsenta_trace import Trace
from backend.src.tools.tsenta_profiles import profile_date_part, profile_history_value
from backend.src.tools.tsenta_answer_policy import requires_human_consent


def test_saved_native_hiringcafe_filters_survive_keyword_search():
    url = 'https://hiringcafe.com/?searchState=%7B%22roleYoeRange%22%3A%5B0%2C5%5D%2C%22searchQuery%22%3A%22old%22%7D'
    state = json.loads(parse_qs(urlsplit(_search_url('SOC analyst', 1, url)).query)['searchState'][0])
    assert state == {'roleYoeRange': [0, 5], 'searchQuery': 'SOC analyst'}


def test_preferences_exclude_wrong_location_salary_and_title():
    jobs = [dict(id='1', title='SOC analyst', location='Chicago, IL', salaryMax=90000),
            dict(id='2', title='SOC analyst', location='New York', salaryMax=90000),
            dict(id='3', title='SOC intern', location='Chicago, IL', salaryMax=90000),
            dict(id='4', title='SOC analyst', remote=True, salaryMax=40000)]
    result = rank_hiringcafe_jobs(jobs, {}, 'SOC', 'Chicago, IL', preferences={
        'strictLocation': True, 'minimumSalary': 70000, 'excludedTitles': 'intern'})
    assert [job['id'] for job in result] == ['1']


def test_experienced_individual_contributor_ranks_realistic_roles_first():
    profile = {
        'personalInformation': {'title': 'Cybersecurity Analyst'},
        'workExperience': [
            {'role': 'Cybersecurity Analyst'},
            {'role': 'Associate Cybersecurity Analyst'},
        ],
        'skillCategories': [{'name': 'Security', 'skills': ['SIEM', 'NIST']}],
    }
    jobs = [
        {'id': 'analyst', 'title': 'Cybersecurity Analyst', 'description': 'SIEM NIST'},
        {'id': 'manager', 'title': 'SOC Manager', 'description': 'Cybersecurity SIEM NIST'},
        {'id': 'intern', 'title': 'Cybersecurity Analyst Internship', 'description': 'SIEM NIST'},
        {'id': 'teacher', 'title': 'Adjunct Cybersecurity Instructor', 'description': 'SIEM NIST'},
    ]
    ranked = rank_hiringcafe_jobs(jobs, profile, 'Cybersecurity')
    scores = {job['id']: job['matchScore'] for job in ranked}
    assert ranked[0]['id'] == 'analyst'
    assert scores['analyst'] > scores['manager']
    assert scores['analyst'] > scores['intern']
    assert scores['analyst'] > scores['teacher']


def test_indexed_avature_history_uses_exact_profile_facts():
    profile = {
        'workExperience': [{
            'company': 'Example Security', 'role': 'SOC Analyst',
            'startDate': 'Jul 2023', 'endDate': 'Present',
            'responsibilities': ['Triaged alerts', 'Built detections'],
        }],
        'education': [{
            'university': 'Example University', 'degree': 'Bachelor of Science',
            'major': 'Cybersecurity', 'endDate': 'May 2023',
        }],
        'certifications': [{'name': 'Security+', 'credentialId': 'CERT-1'}],
    }
    assert profile_history_value(profile, '172-1-0', 'Company *') == 'Example Security'
    assert profile_history_value(profile, '172-2-0', 'Position title *') == 'SOC Analyst'
    assert profile_history_value(profile, '172-3-0', 'Is current position?') == 'Yes'
    assert profile_history_value(profile, '172-4-0', 'Start date *') == 'Jul 2023'
    assert profile_history_value(profile, '172-5-0', 'End date *') == ''
    assert profile_history_value(profile, '790-3-0', 'University') == 'Example University'
    assert profile_history_value(profile, '790-6-0', 'Year Received') == '2023'
    assert profile_history_value(profile, '4522-5-0', 'Name of Certification') == 'Security+'
    assert profile_history_value(profile, '11265', 'Do you have any certifications? *') == 'Yes'


def test_dayforce_history_uses_first_declared_resume_entries():
    profile = {
        'workExperience': [{
            'company': 'Example Security', 'role': 'SOC Analyst',
            'startDate': 'Jul 2023', 'endDate': '',
            'location': 'Chicago, IL',
            'responsibilities': ['Triaged alerts', 'Built detections'],
        }],
        'education': [{
            'university': 'Example University', 'degree': 'Master of Science',
            'major': 'Cybersecurity', 'minor': 'Network Security',
            'startDate': '', 'endDate': '2025-06', 'location': 'Chicago, IL',
        }],
    }
    assert profile_history_value(
        profile, 'work-history-positiontitle-text-input', 'Position Title') == 'SOC Analyst'
    assert profile_history_value(
        profile, 'work-history-employername-text-input', 'Employer Name') == 'Example Security'
    assert profile_history_value(
        profile, 'work-history-currentjob-checkbox', 'Current Job') == 'Yes'
    assert profile_history_value(
        profile, 'work-history-startdate-datepicker', 'Start Date') == '2023-07-01'
    assert profile_history_value(
        profile, 'work-history-dutiesandresponsibilities-textarea-input',
        'Duties and Responsibilities') == 'Triaged alerts\nBuilt detections'
    assert profile_history_value(
        profile, 'education-history-degree-text-input', 'Degree') == 'Master of Science'
    assert profile_history_value(
        profile, 'education-history-schoolname-text-input', 'School') == 'Example University'
    assert profile_history_value(
        profile, 'education-history-enddate-datepicker', 'End Date') == '2025-06-01'
    assert profile_history_value(
        profile, 'education-history-startdate-datepicker', 'Start Date') == ''


def test_llm_answerer_never_sends_indexed_resume_facts_to_model():
    calls = []
    answerer = make_llm_answerer(
        {'workExperience': [{'company': 'Exact Employer'}]},
        llm_cfg={'api_key': 'unused'},
        chat=lambda messages: calls.append(messages) or 'wrong')
    answer = answerer(
        {'field_id': '172-1-0', 'label': 'Company *', 'kind': 'text',
         'required': True, 'options': [], 'hidden': False}, {}, {}, Trace())
    assert answer['value'] == 'Exact Employer'
    assert answer['source'] == 'profile-direct'
    assert calls == []


def test_indexed_degree_semantically_matches_ats_option():
    answerer = make_llm_answerer(
        {'education': [{'degree': 'Bachelor of Science'}]},
        llm_cfg={'api_key': 'unused'}, chat=lambda _messages: 'wrong')
    answer = answerer(
        {'field_id': '790-2-0', 'label': 'Type of degree', 'kind': 'select',
         'required': False,
         'options': [{'value': '24', 'label': "Bachelor's Degree"}],
         'hidden': False}, {}, {}, Trace())
    assert answer == {
        'value': '24', 'source': 'profile-direct',
        'display': "Bachelor's Degree",
    }


def test_current_employment_is_derived_from_profile_not_llm():
    calls = []
    answerer = make_llm_answerer(
        {'workExperience': [{'company': 'Current Co', 'endDate': 'Present'}]},
        llm_cfg={'api_key': 'unused'},
        chat=lambda messages: calls.append(messages) or 'No')
    answer = answerer(
        {'field_id': 'employed', 'label': 'Are you currently employed?',
         'kind': 'radio', 'required': True,
         'options': [{'label': 'Yes', 'value': 'true'},
                     {'label': 'No', 'value': 'false'}], 'hidden': False},
        {}, {}, Trace())
    assert answer == {'value': 'true', 'source': 'profile-direct', 'display': 'Yes'}
    assert calls == []


def test_split_date_controls_use_declared_available_start_date():
    assert profile_date_part('2026-09-15', 'Earliest start date - Day') == '15'
    assert profile_date_part('2026-09-15', 'Earliest start date - Month') == 'September'
    assert profile_date_part('2026-09-15', 'Earliest start date - Year') == '2026'
    answerer = make_llm_answerer(
        {'workPreferences': {'availableStartDate': '2026-09-15'}},
        llm_cfg={'api_key': 'unused'}, chat=lambda _messages: 'wrong')
    answer = answerer(
        {'field_id': 'date-month',
         'label': 'What is your earliest available start date? - Month',
         'kind': 'select', 'required': True,
         'options': [{'label': 'Month', 'value': ''},
                     {'label': 'September', 'value': '9'}], 'hidden': False},
        {}, {}, Trace())
    assert answer == {'value': '9', 'source': 'profile-direct',
                      'display': 'September'}


def test_plural_compensation_expectations_uses_declared_salary():
    answerer = make_llm_answerer(
        {'workPreferences': {'expectedAnnualSalary': '90000'}},
        llm_cfg={'api_key': 'unused'}, chat=lambda _messages: 'wrong')
    answer = answerer(
        {'field_id': 'comp', 'label': 'What are your compensation expectations?',
         'kind': 'number', 'required': True, 'options': [], 'hidden': False},
        {}, {}, Trace())
    assert answer == {'value': '90000', 'source': 'profile-direct',
                      'display': '90000'}


def test_processing_personal_information_is_a_reviewed_consent():
    assert requires_human_consent(
        'Allow us to process your personal information') is True


def test_employment_truth_attestation_is_human_reviewed():
    assert requires_human_consent(
        'The above statements are true and I understand that false information '
        'or material omissions may be cause for discipline or discharge.') is True


def test_hard_requirements_lower_rank_and_explain_why():
    profile = {
        'personalInformation': {
            'title': 'Cybersecurity Analyst',
            'summary': 'Cybersecurity analyst with 5 years of experience',
        },
        'backgroundCheck': {'hasGovernmentClearance': False},
        'workAuthorization': {'citizenshipCountries': []},
        'certifications': [{'name': 'CompTIA Security+'}],
    }
    jobs = [
        {'id': 'fit', 'title': 'Cybersecurity Analyst',
         'description': 'Investigate security alerts and improve detections.'},
        {'id': 'clearance', 'title': 'Cybersecurity Analyst',
         'description': 'An active Secret clearance is required.'},
        {'id': 'obtain', 'title': 'Cybersecurity Analyst',
         'description': 'Must have the ability to obtain and maintain a security clearance.'},
        {'id': 'senior', 'title': 'Cybersecurity Analyst',
         'description': 'Requires 8+ years of cybersecurity experience.'},
        {'id': 'certification', 'title': 'Cybersecurity Analyst',
         'description': 'CISSP certification is required.'},
    ]
    ranked = rank_hiringcafe_jobs(jobs, profile, 'Cybersecurity Analyst')
    by_id = {job['id']: job for job in ranked}
    assert ranked[0]['id'] == 'fit'
    assert by_id['fit']['matchWarnings'] == []
    assert by_id['fit']['matchQuality'] in ('excellent', 'strong', 'good', 'stretch')
    assert by_id['fit']['matchScore'] > by_id['clearance']['matchScore']
    assert by_id['fit']['matchScore'] > by_id['senior']['matchScore']
    assert by_id['fit']['matchScore'] > by_id['certification']['matchScore']
    assert by_id['obtain']['matchScore'] > by_id['clearance']['matchScore']
    assert 'Active security clearance' in by_id['clearance']['matchWarnings'][0]
    assert 'eligibility' in by_id['obtain']['matchWarnings'][0]
    assert '8+ years' in by_id['senior']['matchWarnings'][0]
    assert 'CISSP' in by_id['certification']['matchWarnings'][0]


def test_required_certification_accepts_equivalent_profile_name():
    profile = {
        'personalInformation': {'title': 'SOC Analyst'},
        'certifications': ['CompTIA Security+'],
    }
    jobs = [{'id': 'security-plus', 'title': 'SOC Analyst',
             'description': 'Security+ certification is required.'}]
    ranked = rank_hiringcafe_jobs(jobs, profile, 'SOC Analyst')
    assert ranked[0]['matchWarnings'] == []


def test_standing_instructions_only_apply_explicit_exclusions():
    job = {'title': 'SOC Analyst', 'companyName': 'Acme', 'location': 'Chicago'}
    assert job_matches_standing_instructions(job, 'Prefer cloud security') is True
    assert job_matches_standing_instructions(job, 'Avoid: internships, director') is True
    assert job_matches_standing_instructions(
        {'title': 'Security Internship', 'companyName': 'Acme'},
        'Avoid: internships, director') is False


def test_name_and_eligibility_use_actual_profile():
    profile = {'personalInformation': {'firstName': 'Ada', 'lastName': 'Lovelace'},
               'workAuthorization': {'needsSponsorship': True}}
    answerer = make_llm_answerer(profile, llm_cfg={'api_key': ''})
    for identifier, label, value in [('first_name', 'First name', 'Ada'),
                                     ('fullName', 'Your name', 'Ada Lovelace'),
                                     ('last_name', 'Surname', 'Lovelace')]:
        assert answerer({'field_id': identifier, 'label': label}, profile, {}, None)['value'] == value
    assert answerer({'label': 'Do you require sponsorship?'}, profile, {}, None)['value'] == 'Yes'
    assert answerer({'label': 'Are you Hispanic or Latino?', 'required': True}, profile, {}, None)['source'] == 'skip'


def test_passwords_are_never_generated_or_filled():
    profile = {'personalInformation': {'email': 'candidate@example.test'}}
    answerer = make_llm_answerer(profile, llm_cfg={'api_key': ''})
    answer = answerer({
        'field_id': 'account_password', 'label': 'Choose Password',
        'kind': 'text', 'required': True,
    }, profile, {}, None)
    assert answer['source'] == 'skip'
    assert answer['value'] == ''
    assert 'never' in answer['reason'].lower()


def test_real_browser_fills_unnamed_wrapped_and_autocomplete_fields(monkeypatch):
    from playwright.sync_api import sync_playwright
    from backend.src.tools import tsenta_apply
    monkeypatch.setattr(tsenta_apply, '_human_delay', lambda *args, **kwargs: None)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        page.set_content('''<form>
          <label>First name<input required></label>
          <span id="last-label">Last name</span><input aria-labelledby="last-label" required>
          <input autocomplete="name" required>
        </form>''')
        profile = {'personalInformation': {'firstName': 'Ada', 'lastName': 'Lovelace'}}
        fields = collect_fields(page)
        actions = answer_fields(fields, profile, {}, Trace(), make_llm_answerer(profile, llm_cfg={'api_key': ''}))
        summary = _execute_actions(page, actions, None)
        assert page.locator('input').evaluate_all('(els) => els.map(el => el.value)') == ['Ada', 'Lovelace', 'Ada Lovelace']
        assert len(summary['verified_fields']) == 3
        assert summary['field_failures'] == []
        browser.close()


def test_real_browser_dry_run_walks_next_step_but_never_submits(monkeypatch):
    from playwright.sync_api import sync_playwright
    from backend.src.tools import tsenta_apply
    monkeypatch.setattr(tsenta_apply, '_human_delay', lambda *args, **kwargs: None)
    html = '''<form onsubmit="event.preventDefault(); window.submitted = true">
      <label>First name<input name="first_name" required></label>
      <input name="never_visible" required style="display:none">
      <button type="button" onclick="window.firstName = document.querySelector('input').value;
      document.querySelector('form').innerHTML = '&lt;label&gt;Last name&lt;input name=last_name required&gt;&lt;/label&gt;&lt;button type=submit&gt;Submit application&lt;/button&gt;'">Next</button>
    </form>'''
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        monkeypatch.setattr(tsenta_apply, '_open_form', lambda *args: page.set_content(html))
        original_close = page.close
        monkeypatch.setattr(page, 'close', lambda: None)
        profile = {'personalInformation': {'firstName': 'Ada', 'lastName': 'Lovelace'}}
        result = json.loads(tsenta_apply.apply_job('https://jobs.lever.co/example/fixture', profile,
            dry_run=True, _page_provider=lambda: page,
            answerer=make_llm_answerer(profile, llm_cfg={'api_key': ''})))
        assert result['ok'], result
        assert not result.get('error'), result
        assert result['answers_summary']['steps'] == 2
        assert page.evaluate('window.firstName') == 'Ada'
        assert page.locator('[name=last_name]').input_value() == 'Lovelace'
        assert page.evaluate('Boolean(window.submitted)') is False
        assert result['submitted'] is False
        original_close()
        browser.close()


def test_monitor_apply_requires_clean_preparation_and_opt_in(monkeypatch, tmp_path):
    from webapp import server
    from backend.src.tools.nori_monitor import save_monitor_settings, load_monitor_settings
    monitor_path = str(tmp_path / 'monitor.json')
    monkeypatch.setattr(server, 'MONITOR_PATH', monitor_path)
    monkeypatch.setattr(server, '_load_profile', lambda: {
        'real': True,
        'workAuthorization': {
            'isAuthorizedToWork': True,
            'needsSponsorship': False,
            'reviewedAt': '2026-09-06T00:00:00Z',
        },
    })
    monkeypatch.setattr(server, 'validate_profile', lambda profile: {'valid': True})
    monkeypatch.setattr(server, '_is_test_profile', lambda profile: False)
    monkeypatch.setattr(server, '_load_settings', lambda: {})
    monkeypatch.setattr(server, 'load_feed', lambda: [])
    monkeypatch.setattr(server, 'save_feed', lambda jobs: '{}')
    monkeypatch.setattr(server, '_tracked_urls', lambda: set())
    monkeypatch.setattr(server, 'search_hiringcafe', lambda *args, **kwargs: {
        'ok': True, 'jobs': [{'url': 'https://jobs.lever.co/example/fixture', 'matchScore': 90}]})
    monkeypatch.setattr(server, 'create_job', lambda *args, **kwargs: json.dumps({'ok': True, 'applicationId': 'fixture'}))
    monkeypatch.setattr(server, 'run_job', lambda *args, **kwargs: json.dumps({'ok': True}))
    report = {'answersSummary': {}, 'trace': {'answers': [{'source': 'profile-direct', 'required': True}]}}
    monkeypatch.setattr(server, 'job_report', lambda *args: json.dumps(report))
    submissions = []
    def approve(*args, **kwargs):
        submissions.append(args[0])
        return json.dumps({'ok': True, 'submitted': True})
    monkeypatch.setattr(server, 'review_approve', approve)
    save_monitor_settings({'applicationMode': 'notify'}, monitor_path)
    assert server._run_monitor_cycle()['prepared'] == 0
    assert submissions == []
    save_monitor_settings({'applicationMode': 'prepare'}, monitor_path)
    assert server._run_monitor_cycle()['prepared'] == 1
    assert submissions == []
    save_monitor_settings({'applicationMode': 'apply'}, monitor_path)
    report['answersSummary']['field_failures'] = [{'fieldId': 'first_name'}]
    assert server._run_monitor_cycle()['needsReview'] == 1
    assert submissions == []
    report['answersSummary'] = {}
    report['documents'] = {'resume': {'qualityIssues': ['unsupported number']}}
    assert server._run_monitor_cycle()['needsReview'] == 1
    assert submissions == []
    report['documents'] = {}
    # Lever has not yet passed a real submit + receipt certification, so
    # overnight mode must stop at a ready review draft.
    final_cycle = server._run_monitor_cycle()
    assert final_cycle['applied'] == 0
    assert final_cycle['needsReview'] == 1
    assert submissions == []
    assert load_monitor_settings(monitor_path)['applicationMode'] == 'apply'


def test_monitor_keeps_successful_lane_when_another_lane_fails(monkeypatch, tmp_path):
    from webapp import server
    from backend.src.tools.nori_monitor import save_monitor_settings, load_monitor_settings

    monitor_path = str(tmp_path / 'monitor.json')
    monkeypatch.setattr(server, 'MONITOR_PATH', monitor_path)
    monkeypatch.setattr(server, '_load_profile', lambda: {
        'workAuthorization': {
            'isAuthorizedToWork': True,
            'needsSponsorship': False,
            'reviewedAt': '2026-09-06T00:00:00Z',
        },
    })
    monkeypatch.setattr(server, 'load_feed', lambda: [])
    monkeypatch.setattr(server, 'save_feed', lambda jobs: '{}')

    def search(query, *args, **kwargs):
        if query == 'working':
            return {'ok': True, 'jobs': []}
        return {'ok': False, 'error': 'second-lane-unavailable'}

    monkeypatch.setattr(server, 'search_hiringcafe', search)
    save_monitor_settings({'applicationMode': 'notify', 'lanes': [
        {'id': 'one', 'name': 'Working', 'enabled': True, 'query': 'working'},
        {'id': 'two', 'name': 'Broken', 'enabled': True, 'query': 'broken'},
    ]}, monitor_path)

    result = server._run_monitor_cycle()
    assert result['ok'] is True
    assert result['count'] == 0
    assert result['error'] == 'second-lane-unavailable'
    assert load_monitor_settings(monitor_path)['lastError'] == 'second-lane-unavailable'


def test_monitor_does_not_repeat_local_only_discoveries_as_new(monkeypatch, tmp_path):
    from webapp import server
    from backend.src.tools.nori_monitor import save_monitor_settings

    monitor_path = str(tmp_path / 'monitor.json')
    monkeypatch.setattr(server, 'MONITOR_PATH', monitor_path)
    monkeypatch.setattr(server, '_load_profile', lambda: {})
    monkeypatch.setattr(server, 'load_feed', lambda: [])
    monkeypatch.setattr(server, 'save_feed', lambda jobs: '{}')
    monkeypatch.setattr(server, 'search_hiringcafe', lambda *args, **kwargs: {
        'ok': True,
        'jobs': [{'url': 'https://jobs.example.test/security', 'matchScore': 90}],
    })
    save_monitor_settings({
        'query': 'security', 'applicationMode': 'notify',
        'telegramBotToken': '', 'telegramChatId': '',
    }, monitor_path)

    assert server._run_monitor_cycle()['newCount'] == 1
    assert server._run_monitor_cycle()['newCount'] == 0


def test_telegram_rejects_other_users_and_groups(monkeypatch):
    from backend.src.tools import nori_monitor as monitor
    def callback(update_id, sender, chat_id, chat_type='private'):
        return {'update_id': update_id, 'callback_query': {'id': str(update_id),
            'from': {'id': sender}, 'message': {'chat': {'id': chat_id, 'type': chat_type}},
            'data': 'nori:prepare:fixture'}}
    monkeypatch.setattr(monitor, '_telegram_request', lambda *args: {'ok': True, 'result': [
        callback(1, 999, 42), callback(2, 42, -100, 'group'), callback(3, 42, 42)]})
    result = monitor._telegram_commands({'telegramBotToken': 'fixture', 'telegramChatId': '42'})
    assert [c['id'] for c in result['commands']] == ['3']
    assert result['offset'] == 4


def test_telegram_submit_does_not_bypass_review_checks(monkeypatch, tmp_path):
    from webapp import server
    monkeypatch.setattr(server, 'MONITOR_PATH', str(tmp_path / 'monitor.json'))
    monkeypatch.setattr(server, '_telegram_commands', lambda settings: {'offset': 2, 'commands': [
        {'id': '1', 'data': 'nori:apply:fixture', '_nextOffset': 2}]})
    monkeypatch.setattr(server, '_telegram_request', lambda *args: {'ok': True})
    messages = []
    monkeypatch.setattr(server, '_telegram_status', lambda settings, text, *args: messages.append(text))
    monkeypatch.setattr(server, '_load_profile', lambda: {
        'workAuthorization': {
            'isAuthorizedToWork': True,
            'needsSponsorship': False,
            'reviewedAt': '2026-09-06T00:00:00Z',
        },
    })
    monkeypatch.setattr(server, 'validate_profile', lambda profile: {'valid': True})
    monkeypatch.setattr(server, '_is_test_profile', lambda profile: False)
    monkeypatch.setattr(server, 'job_report', lambda *args: json.dumps({'status': 'review', 'error': 'name not filled'}))
    def forbidden(*args, **kwargs):
        raise AssertionError('Unresolved applications must never submit')
    monkeypatch.setattr(server, 'review_approve', forbidden)
    server._run_telegram_commands({'telegramBotToken': 'fixture', 'telegramChatId': '42'})
    assert len(messages) == 1
    assert 'not ready' in messages[0]


def test_reviewed_answers_stay_stable_until_user_changes_them():
    from backend.src.tools.tsenta_pipeline import _answerer_with_reviewed_values
    answerer = _answerer_with_reviewed_values(lambda *args: {'value': 'new model response'}, [
        {'fieldId': 'why', 'label': 'Why this role?', 'source': 'llm', 'value': 'Reviewed response'}])
    assert answerer({'field_id': 'why', 'label': 'Why this role?'}, {}, {}, None)['value'] == 'Reviewed response'
    assert answerer({'field_id': 'why', 'label': 'Different question'}, {}, {}, None)['value'] == 'new model response'


def test_generated_cover_letter_answers_a_breezy_text_field():
    from backend.src.tools.tsenta_pipeline import _answerer_with_documents
    fallback_calls = []
    answerer = _answerer_with_documents(
        lambda *args: fallback_calls.append(args) or {'value': 'fallback'},
        {'coverLetter': {'useCoverLetter': True,
                         'coverLetterText': 'Reviewed, tailored letter'}},
    )
    answer = answerer(
        {'field_id': 'cCoverLetter', 'label': 'Cover Letter', 'kind': 'textarea'},
        {}, {}, None,
    )
    assert answer == {
        'value': 'Reviewed, tailored letter',
        'source': 'profile-direct',
        'display': 'Cover letter (auto-generated)',
    }
    assert fallback_calls == []


def test_closed_job_board_is_not_an_application():
    import pytest
    from backend.src.tools.tsenta_apply import _assert_open_job
    class ClosedPage:
        def locator(self, selector):
            return self
        def inner_text(self, **kwargs):
            return 'The job you are looking for is no longer open. Search current openings.'
    with pytest.raises(RuntimeError, match='job-closed'):
        _assert_open_job(ClosedPage())


def test_approval_reuses_reviewed_documents(monkeypatch, tmp_path):
    from backend.src.tools import tsenta_pipeline as pipeline, tsenta_documents, tsenta_apply
    docs = {'resume': {'resumeText': 'Reviewed document', 'useOptimizedResume': False},
            'coverLetter': {'coverLetterText': 'Reviewed letter'}}
    job = {'url': 'https://jobs.lever.co/example/fixture', 'companyName': 'Example',
           'jobTitle': 'Analyst', 'jobDescription': 'Security', 'documents': docs}
    generated = []
    monkeypatch.setattr(tsenta_documents, 'documents_for_application', lambda *args, **kwargs: generated.append(True))
    monkeypatch.setattr(tsenta_apply, 'apply_job', lambda *args, **kwargs: json.dumps({'ok': True, 'submitted': True}))
    pipeline._run_apply(job, {}, {}, dry_run=False, confirmed=True,
                        answerer=lambda *args: {}, _page_provider=lambda: None)
    assert generated == []
    assert job['documents']['resume']['resumeText'] == 'Reviewed document'


def test_chatgpt_completion_uses_managed_login_and_read_only_process(monkeypatch):
    from types import SimpleNamespace
    from backend.src.tools import nori_chatgpt
    monkeypatch.setattr(nori_chatgpt, '_codex_executable', lambda: 'codex.exe')
    monkeypatch.setattr(nori_chatgpt, 'chatgpt_login_status', lambda: '{"signedIn":true}')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-be-used')
    def run(args, **kwargs):
        assert '--ignore-user-config' in args and '--ephemeral' in args
        assert args[args.index('--sandbox') + 1] == 'read-only'
        assert 'OPENAI_API_KEY' not in kwargs['env']
        assert 'Requested text' in kwargs['input']
        return SimpleNamespace(returncode=0, stdout='\n'.join([
            json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Completed answer'}}),
            json.dumps({'type': 'turn.completed'})]))
    monkeypatch.setattr(nori_chatgpt.subprocess, 'run', run)
    result = json.loads(nori_chatgpt.chatgpt_completion([{'role': 'user', 'content': 'Requested text'}]))
    assert result == {'ok': True, 'text': 'Completed answer', 'error': ''}


def test_chatgpt_incomplete_turn_never_becomes_an_answer(monkeypatch):
    from types import SimpleNamespace
    from backend.src.tools import nori_chatgpt
    monkeypatch.setattr(nori_chatgpt, '_codex_executable', lambda: 'codex.exe')
    monkeypatch.setattr(nori_chatgpt, 'chatgpt_login_status', lambda: '{"signedIn":true}')
    monkeypatch.setattr(nori_chatgpt.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout=json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Partial'}})))
    result = json.loads(nori_chatgpt.chatgpt_completion([]))
    assert result['ok'] is False and result['text'] == ''


def test_resume_import_preserves_hackerone_and_wrapped_bullets():
    from backend.src.tools.tsenta_resume import _parse_experience
    text = '''EXPERIENCE
PNC Financial Services, Cybersecurity Analyst Jul 2025 - Present | Chicago, IL
• Reviewed vendor controls and
documented risk findings.
HACKERONE SECURITY RESEARCH
HackerOne, Independent Security Researcher 2026 - Present | Remote
• Submitted a finding for preliminary review.
EDUCATION
University, M.S. Cybersecurity'''
    jobs = _parse_experience(text)
    assert [job['company'] for job in jobs] == ['PNC Financial Services', 'HackerOne']
    assert jobs[0]['responsibilities'] == ['Reviewed vendor controls and documented risk findings.']
    assert jobs[0]['isCurrentRole'] is True
    assert jobs[1]['startDate'] == '2026'
    assert jobs[1]['isCurrentRole'] is True
