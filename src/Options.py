from Options import PerGameCommonOptions, FreeText, Toggle, DefaultOnToggle, Choice, TextChoice, Range, NamedRange, DeathLink, \
    OptionGroup, StartInventoryPool, Visibility, item_and_loc_options
from .hooks.Options import before_options_defined, after_options_defined, before_option_groups_created, after_option_groups_created
from .Data import category_table, game_table, option_table
from .Helpers import convertToLongString
from .Locations import victory_names
from .Items import item_table
from .Game import starting_items

from dataclasses import make_dataclass
from typing import List
import logging


class FillerTrapPercent(Range):
    """How many fillers will be replaced with traps. 0 means no additional traps, 100 means all fillers are traps."""
    range_end = 100

def createChoiceOptions(values: dict, aliases: dict) -> dict:
    values = {'option_' + i: v for i, v in values.items()}
    aliases = {'alias_' + i: v for i, v in aliases.items()}
    return {**values, **aliases}

def convertOptionVisibility(input) -> Visibility:
    visibility = Visibility.all
    if isinstance(input, list):
        visibility = Visibility.none
        for type in input:
            visibility |= Visibility[type.lower()]

    elif isinstance(input,str):
        if input.startswith('0b'):
            visibility = int(input, base=0)
        else:
            visibility = Visibility[input.lower()]

    elif isinstance(input, int):
        visibility = input
    return visibility


manual_option_groups = {}
def addOptionToGroup(option_name: str, group: str):
    if group not in manual_option_groups.keys():
        manual_option_groups[group] = []
    if manual_options.get(option_name) and manual_options[option_name] not in manual_option_groups[group]:
        manual_option_groups[group].append(manual_options[option_name])

######################
# Manual's default options
######################

manual_options = before_options_defined({})
manual_options["start_inventory_from_pool"] = StartInventoryPool

if len(victory_names) > 1:
    if manual_options.get('goal'):
        logging.warning("Existing Goal option found created via Hooks, it will be overwritten by Manual's generated Goal option.\nIf you want to support old yaml you will need to add alias in after_options_defined")

    goal = {'option_' + v: i for i, v in enumerate(victory_names)}

    manual_options['goal'] = type('goal', (Choice,), dict(goal))
    manual_options['goal'].__doc__ = "Choose your victory condition."


if any(item.get('trap') for item in item_table):
    manual_options["filler_traps"] = FillerTrapPercent

if game_table.get("death_link"):
    manual_options["death_link"] = DeathLink


######################
# Option.json options generation
######################

supported_option_types = ["Toggle", "Choice", "Range"]
for option_name, option in option_table.get('data', {}).items():
    if option_name.startswith('_'): #To allow commenting out options
        continue

    if manual_options.get(option_name): #Override Mode
        original_doc = str(manual_options[option_name].__doc__)
        if option_name == 'goal':
            new_goal = createChoiceOptions({}, option.get('aliases', {}))
            if new_goal: #only recreate if needed
                new_goal = {**goal, **new_goal}
                manual_options['goal'] = type('goal', (Choice,), dict(new_goal))

        if option.get('display_name'):
            manual_options[option_name].display_name = option['display_name']

        manual_options[option_name].__doc__ = convertToLongString(option.get('description', original_doc))
        if option.get('rich_text_doc'):
            manual_options[option_name].rich_text_doc = option["rich_text_doc"]

        if option.get('default'):
            manual_options[option_name].default = option['default']

        if option.get('hidden'):
            manual_options[option_name].visibility = Visibility.none
        elif option.get('visibility'):
            manual_options[option_name].visibility = convertOptionVisibility(option['visibility'])

        if option.get('group', ""):
            addOptionToGroup(option_name, option['group'])

        continue

    if option_name not in manual_options:
        option_type = option.get('type', "").title()

        if option_type not in supported_option_types:
            raise Exception(f'Option {option_name} in options.json has an invalid type of "{option["type"]}".\nIt must be one of the folowing: {supported_option_types}')

        args = {'display_name': option.get('display_name', option_name)}

        if option_type == "Toggle":
            value = option.get('default', False)
            option_class = DefaultOnToggle if value else Toggle

        elif option_type == "Choice":
            args = {**args, **createChoiceOptions(option.get('values'), option.get('aliases', {}))}
            option_class = TextChoice if option.get("allow_custom_value", False) else Choice

        elif option_type == "Range":
            args['range_start'] = option.get('range_start', 0)
            args['range_end'] = option.get('range_end', 1)
            if option.get('values'):
                args['special_range_names'] = {l.lower(): v for l, v in option['values'].items()}
                args['special_range_names']['default'] = option.get('default', args['range_start'])
            option_class = NamedRange if option.get('values') else Range

        if option.get('default'):
            args['default'] = option['default']

        if option.get('rich_text_doc',None) is not None:
            args["rich_text_doc"] = option["rich_text_doc"]

        if option.get('hidden'):
            args['visibility'] = Visibility.none
        elif option.get('visibility'):
            args['visibility'] = convertOptionVisibility(option['visibility'])

        manual_options[option_name] = type(option_name, (option_class,), args )
        manual_options[option_name].__doc__ = convertToLongString(option.get('description', "an Option"))

    if option.get('group'):
        addOptionToGroup(option_name, option['group'])

######################
# category and starting_items options
######################

for category in category_table:
    for option_name in category_table[category].get("yaml_option", []):
        if option_name[0] == "!":
            option_name = option_name[1:]
        if option_name not in manual_options:
            manual_options[option_name] = type(option_name, (DefaultOnToggle,), {"default": True})
            manual_options[option_name].__doc__ = "Should items/locations linked to this option be enabled?"

if starting_items:
    for starting_items in starting_items:
        if starting_items.get("yaml_option"):
            for option_name in starting_items["yaml_option"]:
                if option_name[0] == "!":
                    option_name = option_name[1:]
                if option_name not in manual_options:
                    manual_options[option_name] = type(option_name, (DefaultOnToggle,), {"default": True})
                    manual_options[option_name].__doc__ = "Should items/locations linked to this option be enabled?"

######################
# OptionGroups Creation
######################

def make_options_group() -> list[OptionGroup]:
    global manual_option_groups
    manual_option_groups = before_option_groups_created(manual_option_groups)
    option_groups: List[OptionGroup] = []

    # For some reason, unless they are added manually, the base item and loc option don't get grouped as they should
    base_item_loc_group = item_and_loc_options

    if manual_option_groups:
        if 'Item & Location Options' in manual_option_groups.keys():
            base_item_loc_group.extend(manual_option_groups['Item & Location Options'])
            manual_option_groups.pop('Item & Location Options')

        for group, options in manual_option_groups.items():
            option_groups.append(OptionGroup(group, options))

    option_groups.append(OptionGroup('Item & Location Options', base_item_loc_group, True))

    return after_option_groups_created(option_groups)

manual_options = after_options_defined(manual_options)
manual_options_data = make_dataclass('ManualOptionsClass', manual_options.items(), bases=(PerGameCommonOptions,))
