import multiprocessing
from six.moves import configparser
import six


class AnswerStore(object):
    """
    AnswerStore handles storing and loading answer files for user questions.
    """
    def __init__(self, manager=None):
        """
        Initialize the answer store.
        :param manager: Passes through a given instance of multiprocessing.Manager() to use, by default it creates
                        an own instance.
        """
        self._manager = manager or multiprocessing.Manager()
        self._storage = self._manager.dict()

    def answer(self, scope, key, value):
        dialog_scope = self._storage.get(scope, {})
        dialog_scope[key] = value
        # As _storage is a dict proxy, we have to explicitly update the object via __setitem__
        # Otherwise we won't get the update propagated to the parent process
        # So don't even bother updating this to some more 'pythonic' coding style
        self._storage[scope] = dialog_scope

    def load(self, answer_file):
        """
        Loads an answer file from the given location and updates the loaded data with it.

        :param answer_file: Path to the answer file to load.
        :return: None
        """
        conf = configparser.SafeConfigParser(allow_no_value=True)
        conf.read(answer_file)
        for section in conf.sections():
            self._storage[section] = self._manager.dict(conf.items(section=section, raw=True))

    def load_and_translate_for_workflow(self, answer_file, workflow):
        """
        Loads an answer file from the given location and updates the loaded data with it and translates the data to
        the correct value types based on the dialogs in the given workflow.

        :param answer_file: Path to the answer file to load.
        :param workflow:
        :return: None
        """
        conf = configparser.SafeConfigParser(allow_no_value=True)
        conf.read(answer_file)
        for section in conf.sections():
            self._storage[section] = dict(conf.items(section=section, raw=True))
        self.translate_for_workflow(workflow)

    def get(self, scope, fallback=None):
        """
        Dict compatible interface to get a sub dictionary by dialog scope.

        :param scope: Scope of the data to retrieve.
        :param fallback: Fallback value to return if not found.
        :return:
        """
        return self._storage.get(scope, fallback)

    def translate_for_workflow(self, workflow):
        """
        Translates the data for all dialogs in the current workflow.

        :param workflow: Instance of a workflow to translate all dialogs from.
        :type workflow: :py:class:`leapp.workflows.Workflow`
        :return: None
        """
        for dialog in self._get_dialogs(workflow):
            self.translate(dialog)

    def translate(self, dialog):
        """
        Translates configuration values from their string form to the corresponding value format based on the given
        dialog.

        :param dialog: A dialog instance to translate the data for.
        :type dialog: :py:class:`leapp.dialogs.dialog.Dialog`
        :return: None
        """
        entry = self._storage.get(dialog.scope)
        if entry:
            for component in dialog.components:
                if component.key in entry and isinstance(entry[component.key], six.string_types):
                    if component.value_type is bool:
                        entry[component.key] = entry[component.key].lower() == 'true'
                    elif component.value_type is int:
                        entry[component.key] = int(entry[component.key])
                    elif component.value_type is tuple:
                        elements = entry[component.key].split(';')
                        entry[component.key] = tuple(set(elements).intersection(component.choices))
                    elif hasattr(component, 'choices'):
                        value = entry[component.key]
                        entry[component.key] = value if value in component.choices else None
                    component.value = entry.get(component.key)
            self._storage.update({dialog.scope: entry})

    @staticmethod
    def _get_dialogs(workflow):
        """
        Retrieve all dialogs from the actors of the given workflow.

        :param workflow: Workflow to retrieve all questions from.

        :return: List of dialogs from the actors.
        """
        dialogs = []
        for phase in workflow.phase_actors:
            for stage in phase[1:]:
                for actor in stage.actors:
                    dialogs.extend(actor.dialogs)
        return dialogs

    def generate_for_workflow(self, workflow, answer_file_path):
        """
        Generates an answer file for the dialogs of the given workflow and stores it to `answer_file_path`.
        :param workflow: Instance of :py:class:`leapp.workflows.Workflow` to retrieve all dialogs from.
        :param answer_file_path: The path of where to store the answer file to.
        :return: None
        """
        self.generate(self._get_dialogs(workflow), answer_file_path)

    def generate(self, dialogs, answer_file_path):
        """
        Generates an answer file for the given dialogs and stores it to `answer_file_path`.
        :param dialogs:
        :param answer_file_path:
        :return:
        """
        with open(answer_file_path, 'w') as f:
            for dialog in dialogs:
                if not dialog.components:
                    # Skip dialogs without questions
                    continue

                f.writelines([
                    '[{}]\n'.format(dialog.scope),
                    '# {:<20}{}\n'.format('Title:', dialog.title),
                    '# {:<20}{}\n'.format('Reason:', dialog.reason)
                ])

                for component in dialog.components:
                    answer = self._storage.get(dialog.scope, {}).get(component.key)
                    default = component.default
                    choices = ''
                    answer_entry = ''
                    if hasattr(component, 'choices'):
                        choices += '# Available choices:\n'
                        for choice in component.choices:
                            choices += '# - {}\n'.format(choice)
                        if component.value_type is tuple:
                            default = ';'.join(component.default)
                            answer = ';'.join(answer) if answer else answer
                            answer_entry = '#\n# Values are separated by semi-colon ";"\n'
                    if answer:
                        answer_entry += '{key} = {value}\n'.format(key=component.key, value=answer)
                    else:
                        answer_entry += '# Unanswered question. Uncomment the following line with your answer\n'
                        answer_entry += '# {key} = {value}\n'.format(key=component.key, value=default or '')

                    f.writelines([
                        '# {}\n'.format(' {}.{} '.format(dialog.scope, component.key).center(77, '=')),
                        '# {:<20}{}\n'.format('Label:', component.label),
                        '# {:<20}{}\n'.format('Description:', component.description),
                        '# {:<20}{}\n'.format('Type:', component.value_type.__name__),
                        '# {:<20}{}\n'.format('Default:', default),
                        choices,
                        answer_entry,
                        '\n'
                    ])
